# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

import array
import asyncio
import time
import typing
from io import BytesIO
import math
import os
from asyncio import StreamReader, StreamWriter, Task, IncompleteReadError
from typing import Any
import logging

import bitcoinx
from bitcoinx import double_sha256, read_varint

from .constants import BLOCK_HEADER_LENGTH
from .preprocessor import unpack_varint, tx_preprocessor
from .types import (
    BlockType,
    BlockChunkData,
    BlockDataMsg, BitcoinClientMode, Reject,
)
from .commands import BLOCK, EXTMSG, VERACK
from .utils import create_task

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

if typing.TYPE_CHECKING:
    from .handlers import HandlersDefault
    from .deserializer import MessageHeader, Inv


class GracefulDisconnect(Exception):
    pass


class BitcoinP2PClientError(Exception):
    pass


DEFAULT_LARGE_MESSAGE_LIMIT = 32 * 1024 * 1024  # 32MB


class BitcoinClient:
    """
    Big blocks are blocks larger than large_message_limit
    Small blocks are blocks less than or equal to large_message_limit
    """

    HEADER_LENGTH = 24
    EXTENDED_HEADER_LENGTH = 24 + 20
    MESSAGE_HANDLER_TASK_COUNT = 10  # adds concurrency to message handling

    def __init__(
        self,
        id: int,
        remote_host: str,
        remote_port: int,
        message_handler: 'HandlersDefault',
        local_host: str = "127.0.0.1",
        local_port: int = 8333,
        user_agent: str = "",
        reader: StreamReader | None = None,
        writer: StreamWriter | None = None,
        large_message_limit: int = DEFAULT_LARGE_MESSAGE_LIMIT,
        mode: BitcoinClientMode = BitcoinClientMode.SIMPLE,
        relay_transactions: bool = True
    ) -> None:
        self.relay_transactions: bool = relay_transactions
        self.id = id
        self.logger = logging.getLogger(f"bitcoin-client(id={self.id})")
        self.logger.setLevel(logging.DEBUG)
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.local_host = local_host
        self.local_port = local_port
        self.user_agent = user_agent
        self.message_handler = message_handler
        self.net_config = message_handler.net_config
        self.serializer = message_handler.serializer
        self.deserializer = message_handler.deserializer
        self.large_message_limit = large_message_limit

        self.message_queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(maxsize=100)
        self.reader: StreamReader | None = reader
        self.writer: StreamWriter | None = writer

        self.connection_lost_event = asyncio.Event()
        self.handshake_complete_event = asyncio.Event()
        self.connected = False
        self.closing = False
        self.remote_start_height = 0  # not updated after connecting

        self.mode = mode
        # If BitcoinClientMode.SIMPLE is set then messages are passed to these queues
        self.headers_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=100)
        self.inv_queue: asyncio.Queue[list[Inv] | None] = asyncio.Queue(maxsize=100)
        # On tx broadcast wait for Rejection. Correlation with tx_hash is necessary
        # to enable concurrent usage of the broadcast_transaction method
        self.tx_reject_queue_map: dict[bytes, Reject | None] = {}  # tx_hash -> Reject

        self.tasks: list[Task[Any]] = []

    async def __aenter__(self) -> 'BitcoinClient':
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):  # type: ignore
        await self.close()

    async def connect(self) -> None:
        """raises `ConnectionResetError`"""
        if self.reader is None and self.writer is None:
            self.reader, self.writer = await asyncio.open_connection(host=self.remote_host, port=self.remote_port)
        self.connected = True
        self.logger.debug(
            f"Connection made to peer: {self.remote_host}:{self.remote_port} (peer_id={self.id})"
        )
        assert self.reader is not None
        assert self.writer is not None
        self.tasks.append(create_task(self.start_session()))
        await self.handshake_complete_event.wait()

    async def read_header(self, stream: BytesIO) -> 'MessageHeader':
        assert self.reader is not None
        header: 'MessageHeader' = self.deserializer.deserialize_message_header(stream)
        if header.command == EXTMSG:
            if stream.tell() < self.EXTENDED_HEADER_LENGTH:
                try:
                    data = await self.reader.readexactly(self.EXTENDED_HEADER_LENGTH - stream.tell())
                    stream.write(data)
                except IncompleteReadError:
                    raise ConnectionResetError
            stream.seek(0)
            return self.deserializer.deserialize_extended_message_header(stream)
        return header

    async def read_small_payload(self, stream: BytesIO, header: 'MessageHeader') -> bytes:
        assert self.reader is not None
        stream.seek(0, os.SEEK_END)
        try:
            data = await self.reader.readexactly(header.length)
            stream.write(data)
        except IncompleteReadError:
            raise ConnectionResetError

        stream.seek(0)
        return stream.read(header.length)

    async def _session(self) -> None:
        """raises `ConnectionResetError`"""
        assert self.reader is not None

        for i in range(self.MESSAGE_HANDLER_TASK_COUNT):
            self.tasks.append(create_task(self.handle_message_task_async()))
        self.tasks.append(create_task(self.keepalive()))
        self.tasks.append(create_task(self.handshake(self.local_host, self.local_port)))

        while True:
            # Header
            try:
                stream = BytesIO()
                data = await self.reader.readexactly(self.HEADER_LENGTH)
                stream.seek(0, os.SEEK_END)
                stream.write(data)
            except IncompleteReadError:
                raise ConnectionResetError

            stream.seek(0)
            header = await self.read_header(stream)

            # Payload
            stream = BytesIO()
            if header.length < self.large_message_limit:
                payload = await self.read_small_payload(stream, header)
                if header.command == BLOCK:
                    await self.handle_small_block(payload, header.length)
                else:
                    await self.message_queue.put((header.command, payload))
            elif header.command == BLOCK:
                await self.handle_big_block(stream, header.length)
            else:
                # tx, cmpctblock, blocktxn, getblocktxn can be large
                payload = await self.read_small_payload(stream, header)
                await self.message_queue.put((header.command, payload))

    async def wait_for_connection(self) -> None:
        """Keep retrying until the node comes online"""
        # TODO exponential backoff
        while True:
            try:
                await self.connect()
                return
            except ConnectionRefusedError:
                self.logger.debug(
                    f"Bitcoin node on:  {self.remote_host}:{self.remote_port} unavailable. "
                    f"Waiting."
                )
                await asyncio.sleep(30)

    def send_message(self, message: bytes) -> None:
        assert self.writer is not None
        self.writer.write(message)

    async def close(self) -> None:
        self.logger.info("Closing bitcoin p2p socket connection gracefully")
        self.closing = True
        if self.writer and not self.writer.is_closing():
            self.writer.close()
        self.connected = False
        self.connection_lost_event.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
                await asyncio.sleep(0)  # Let cancelling be scheduled
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    self.logger.exception("Unexpected exception in close")

    async def handle_message_task_async(self) -> None:
        while True:
            command, message = await self.message_queue.get()
            handler_func_name = "on_" + command
            try:
                handler_func = getattr(self.message_handler, handler_func_name)
            except AttributeError:
                self.logger.debug(f"Handler not implemented for command: {command}")
                continue

            await handler_func(message, self)
            if command == VERACK:
                self.handshake_complete_event.set()

    async def handle_big_block(self, stream: BytesIO, size: int) -> None:
        """The `on_block_chunk` allows for intercepting of the chunks of a larger block (possibly 4GB in size)
        whilst still in memory for:
        - writing chunks incrementally to disc
        - handing off the chunks to worker processes

        In this way, arbitrarily large blocks can be handled without exceeding memory allocation limits.
        """
        assert self.reader is not None
        chunk_num = 0
        last_tx_offset_in_chunk: int | None = None
        num_chunks = math.ceil(size / self.large_message_limit)
        block_bytes_read = 0
        tx_offsets_all: "array.ArrayType[int]" = array.array("Q")
        block_hash = bytes()
        adjustment = 0
        while block_bytes_read < size:
            stream.seek(0, os.SEEK_END)
            try:
                if (size - block_bytes_read) >= self.large_message_limit:
                    data = await self.reader.readexactly(self.large_message_limit)
                else:
                    data = await self.reader.readexactly(size - block_bytes_read)
            except IncompleteReadError:
                raise ConnectionResetError
            block_bytes_read += len(data)
            stream.write(data)

            stream.seek(0)
            next_chunk = stream.read()
            chunk_num += 1

            # Find the offsets of the transactions in the block
            # so we can provide the chunks sized to the nearest
            # whole transaction. This allows parallel processing.
            if chunk_num == 1:
                stream.seek(0)
                raw_block_header = stream.read(BLOCK_HEADER_LENGTH)
                block_hash = double_sha256(raw_block_header)
                pos_before = stream.tell()
                tx_count = read_varint(stream.read)
                var_int_size = stream.tell() - pos_before
                offset = 80 + var_int_size
            else:
                offset = 0
                assert last_tx_offset_in_chunk is not None
                adjustment = last_tx_offset_in_chunk

            tx_offsets_for_chunk, last_tx_offset_in_chunk = tx_preprocessor(
                next_chunk, offset, adjustment
            )
            tx_offsets_all.extend(tx_offsets_for_chunk)
            len_slice = last_tx_offset_in_chunk - adjustment
            stream.seek(len_slice)
            stream = BytesIO(stream.read())

            # `tx_offsets_for_chunk` corresponds exactly to `slice_for_worker`
            slice_for_worker = next_chunk[:len_slice]
            # ---------- TxOffsets logic end ---------- #

            block_chunk_data = BlockChunkData(
                chunk_num,
                num_chunks,
                block_hash,
                slice_for_worker,
                tx_offsets_for_chunk,
            )
            await self.message_handler.on_block_chunk(block_chunk_data, self)

        assert last_tx_offset_in_chunk == size
        block_data_msg = BlockDataMsg(
            BlockType.BIG_BLOCK,
            block_hash,
            array.array("Q", tx_offsets_all),
            size,
            small_block_data=None
        )
        stream.seek(0, os.SEEK_END)
        assert stream.tell() == 0
        await self.message_handler.on_block(block_data_msg, self)

    async def handle_small_block(self, buffer: bytes, size: int) -> None:
        """
        If `block_type` is BlockType.SMALL_BLOCK, process as a single chunk in memory and
        call the `on_block` handler immediately (without any calls to `on_block_chunk`

        raises `ConnectionResetError`
        """
        # Init local variables - Keeping them local avoids polluting instance state
        tx_offsets_all: "array.ArrayType[int]" = array.array("Q")
        adjustment = 0
        raw_block = buffer
        raw_block_header = raw_block[0:80]
        block_hash = double_sha256(raw_block_header)
        tx_count, var_int_size = unpack_varint(raw_block[80:89], 0)
        offset = 80 + var_int_size
        tx_offsets_for_chunk, last_tx_offset_in_chunk = tx_preprocessor(raw_block, offset, adjustment)
        tx_offsets_all.extend(tx_offsets_for_chunk)
        assert last_tx_offset_in_chunk == len(raw_block) == size
        block_data_msg = BlockDataMsg(
            BlockType.SMALL_BLOCK,
            block_hash,
            array.array("Q", tx_offsets_all),
            size,
            raw_block
        )
        await self.message_handler.on_block(block_data_msg, self)

    async def send_version(self, local_host: str, local_port: int) -> None:
        message = self.serializer.version(
            recv_host=self.remote_host,
            recv_port=self.remote_port,
            send_host=local_host,
            send_port=local_port,
            user_agent=self.user_agent,
            relay=int(self.relay_transactions)
        )
        self.send_message(message)

    async def handshake(self, local_host: str, local_port: int) -> None:
        create_task(self.send_version(local_host, local_port))
        await self.handshake_complete_event.wait()

    async def start_session(self) -> None:
        """Reconnection logic needs to be managed by the ClientManager"""
        try:
            self.connection_lost_event.clear()  # If we are reconnecting, this might be set
            await self._session()
        except ConnectionResetError:
            self.logger.error(f"Bitcoin node disconnected")
        finally:
            if self.writer and not self.writer.is_closing():
                await self.close()

    async def keepalive(self) -> None:
        await self.handshake_complete_event.wait()
        self.logger.debug(f"Handshake event complete")
        await asyncio.sleep(2)
        while True:
            ping_msg = self.serializer.ping()
            self.send_message(ping_msg)
            await asyncio.sleep(2 * 60)  # Matches bitcoin-sv/net/net.h constant PING_INTERVAL

    async def listen(self) -> None:
        """Should periodically check for disconnection and try to reconnect on a sensible
        time schedule (frequently at first) and then less frequently."""
        while not self.closing:
            await asyncio.sleep(2)

    # Specialized methods for sending messages
    async def broadcast_transaction(self, rawtx: bytes, wait_time: float=10.0,
            check_malformed: bool = True) -> Reject | None:
        """This method is part of the BitcoinClientMode.SIMPLE API for apps that care more
        about a user-friendly API than raw performance.

        If the transaction is rejected by network rules it will immediately return a Reject
        message with the reason.
        If the transaction is not rejected then it will return None.

        The BitcoinClientManager has a wrapper around this function which will additionally
        listen to other peers for evidence that the transaction is being relayed around the
        network.
        """
        if self.mode != BitcoinClientMode.SIMPLE:
            raise ValueError("This helper method is only available in BitcoinClientMode.SIMPLE mode")

        tx_hash = double_sha256(rawtx)
        if tx_hash in self.tx_reject_queue_map:
            raise ValueError("This transaction was already broadcast to this peer")

        try:
            # Re-parsing the transaction here is inefficient but the REJECT_MALFORMED
            # message doesn't contain an item_hash so cannot be inserted into the
            # tx_reject_queue_map from the handler.
            # If concurrent transaction broadcasts are happening there would be no way
            # of knowing which transaction was the problematic one
            # If you're 100% sure you are not producing malformed transactions this
            # check can be skipped for performance reasons with check_malformed.
            # In most cases it will not be noticeable. Bitcoinx parses transactions
            # at a rate of around 50,000 per second.
            if check_malformed:
                bitcoinx.Tx.from_bytes(rawtx)
        except Exception:
            reject_msg: Reject | None = Reject(message='tx', ccode_translation='REJECT_MALFORMED',
                reason='error parsing message', item_hash='')
            return reject_msg

        # Broadcast
        try:
            self.tx_reject_queue_map[tx_hash] = None
            message = self.serializer.tx(rawtx)
            self.send_message(message)

            # Listen for rejection
            time_start = time.time()
            while (time.time() - time_start) < wait_time:
                reject_msg = self.tx_reject_queue_map[tx_hash]
                if reject_msg is not None:
                    return reject_msg
                await asyncio.sleep(0.2)
            return None
        finally:
            del self.tx_reject_queue_map[tx_hash]

    async def get_headers(self, hash_count: int, block_locator_hashes: list[bytes],
            hash_stop: bytes) -> bytes | None:
        if not self.mode:
            raise ValueError("This helper method is only available in BitcoinClientMode.SIMPLE mode")

        message = self.serializer.getheaders(
            hash_count=hash_count,
            block_locator_hashes=block_locator_hashes,
            hash_stop=hash_stop
        )
        self.send_message(message)
        headers = await self.headers_queue.get()
        return headers
