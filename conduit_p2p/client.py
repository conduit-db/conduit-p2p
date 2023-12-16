# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

import array
import asyncio
import typing
from io import BytesIO
import math
import os
from asyncio import StreamReader, StreamWriter, Task, IncompleteReadError
from typing import Any
import logging

from bitcoinx import double_sha256, read_varint

from .constants import BLOCK_HEADER_LENGTH
from .preprocessor import unpack_varint, tx_preprocessor
from .types import (
    BlockType,
    BlockChunkData,
    BlockDataMsg,
)
from .commands import BLOCK, EXTMSG, VERACK
from .utils import create_task

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

if typing.TYPE_CHECKING:
    from .handlers import HandlersDefault
    from .deserializer import MessageHeader


class GracefulDisconnect(Exception):
    pass


class BitcoinP2PClientError(Exception):
    pass


DEFAULT_LARGE_MESSAGE_LIMIT = 32 * 1024 * 1024  # 32MB


class BitcoinClient:
    """
    Big blocks are blocks larger than size.BUFFER_SIZE and are streamed directly to a
    temporary file and just need to be os.move'd into the
    correct final resting place.

    Small blocks are blocks less than or equal to size.BUFFER_SIZE and are better to be
    concatenated in memory before writing them all to the same file. Otherwise the spinning HDD
    discs will 'stutter' with too many tiny writes.
    """

    HEADER_LENGTH = 24
    EXTENDED_HEADER_LENGTH = 24 + 20
    MESSAGE_HANDLER_TASK_COUNT = 4  # adds concurrency to message handling

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
        large_message_limit: int = DEFAULT_LARGE_MESSAGE_LIMIT
    ) -> None:
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

        self.tasks: list[Task[Any]] = []
        # TODO(prioritisation): Track the chain tip of each peer and the time last connected. Ideally would also have
        #  more sophisticated metrics on things like ping_ms and download rate during a large block download.

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

    async def wait_for_connection(self) -> None:
        """Keep retrying until the node comes online"""
        while True:
            try:
                await self.connect()
                return
            except ConnectionRefusedError:
                self.logger.debug(
                    f"Bitcoin node on:  {self.remote_host}:{self.remote_port} currently unavailable "
                    f"- waiting..."
                )
                await asyncio.sleep(5)

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
                    import pdb; pdb.set_trace()  # fmt: skip

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
            user_agent=self.user_agent
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

    def broadcast_transaction(self, rawtx: bytes) -> None:
        message = self.serializer.tx(rawtx)
        self.send_message(message)

    async def listen(self) -> None:
        """Should periodically check for disconnection and try to reconnect on a sensible
        time schedule (frequently at first) and then less frequently."""
        while not self.closing:
            await asyncio.sleep(2)
