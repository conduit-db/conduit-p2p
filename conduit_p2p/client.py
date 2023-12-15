# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

import array
import asyncio
from io import BytesIO
import math
import os
from asyncio import StreamReader, StreamWriter, Task, IncompleteReadError
from typing import Any
import logging

from bitcoinx import double_sha256, read_varint

from .constants import BLOCK_HEADER_LENGTH
from .deserializer import Deserializer, MessageHeader
from .networks import NetworkConfig
from .serializer import Serializer
from .preprocessor import unpack_varint, tx_preprocessor
from .types import (
    BlockType,
    BlockChunkData,
    BlockDataMsg,
    BitcoinPeerInstance,
)
from .commands import BLOCK, EXTMSG, VERACK
from .handlers import HandlersDefault
from .utils import create_task

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


class GracefulDisconnect(Exception):
    pass


class BitcoinP2PClientError(Exception):
    pass


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
    LARGE_MESSAGE_LIMIT = 32 * 1024 * 1024  # 32MB
    MESSAGE_HANDLER_TASK_COUNT = 4  # adds concurrency to message handling

    def __init__(
        self,
        id: int,
        remote_host: str,
        remote_port: int,
        message_handler: HandlersDefault,
        net_config: NetworkConfig,
        local_host: str = "127.0.0.1",
        local_port: int = 8333,
        reader: StreamReader | None = None,
        writer: StreamWriter | None = None,
    ) -> None:
        self.id = id
        self.logger = logging.getLogger(f"bitcoin-p2p-socket(id={self.id})")
        self.logger.setLevel(logging.DEBUG)
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.local_host = local_host
        self.local_port = local_port
        self.message_handler = message_handler
        self.net_config = net_config
        self.serializer = Serializer(net_config)
        self.deserializer = Deserializer(net_config)

        self.message_queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(maxsize=100)
        self.reader: StreamReader | None = reader
        self.writer: StreamWriter | None = writer

        self.connection_lost_event = asyncio.Event()
        self.handshake_complete_event = asyncio.Event()
        self.connected = False

        self.tasks: list[Task[Any]] = []

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
        self.peer = BitcoinPeerInstance(self.reader, self.writer, self.remote_host, self.remote_port, self.id)
        self.tasks.append(create_task(self.start_session()))

    async def read_header(self, stream: BytesIO) -> MessageHeader:
        assert self.reader is not None
        header: MessageHeader = self.deserializer.deserialize_message_header(stream)
        if header.command == EXTMSG:
            if stream.tell() < self.EXTENDED_HEADER_LENGTH:
                data = await self.reader.readexactly(self.EXTENDED_HEADER_LENGTH - stream.tell())
                stream.write(data)
            stream.seek(0)
            return self.deserializer.deserialize_extended_message_header(stream)
        return header

    async def read_small_payload(self, stream: BytesIO, header: MessageHeader) -> bytes:
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
        assert self.peer is not None

        for i in range(self.MESSAGE_HANDLER_TASK_COUNT):
            self.tasks.append(create_task(self.handle_message_task_async()))
        self.tasks.append(create_task(self.keepalive()))
        self.tasks.append(create_task(self.handshake(self.local_host, self.local_port)))

        stream = BytesIO()
        while True:
            # Header
            try:
                data = await self.reader.readexactly(self.HEADER_LENGTH)
                stream.seek(0, os.SEEK_END)
                stream.write(data)
            except IncompleteReadError:
                raise ConnectionResetError

            stream.seek(0)
            header = await self.read_header(stream)

            # Payload(s)
            stream = BytesIO()
            if header.length < self.LARGE_MESSAGE_LIMIT:
                payload = await self.read_small_payload(stream, header)
                if header.command == BLOCK:
                    await self.handle_small_block(payload, header.length)
                else:
                    await self.message_queue.put((header.command, payload))
                stream = BytesIO(stream.read())
            elif header.command == BLOCK:
                await self.handle_big_block(stream, header.length)
                stream = BytesIO(stream.read())

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

    async def send_message(self, message: bytes) -> None:
        assert self.writer is not None
        self.writer.write(message)

    async def close_connection(self) -> None:
        self.logger.info("Closing bitcoin p2p socket connection gracefully")
        if self.writer and not self.writer.is_closing():
            self.writer.close()
        self.connected = False
        self.connection_lost_event.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def handle_message_task_async(self) -> None:
        while True:
            command, message = await self.message_queue.get()
            handler_func_name = "on_" + command
            try:
                handler_func = getattr(self.message_handler, handler_func_name)
                await handler_func(message, self.peer)
            except AttributeError:
                self.logger.debug(f"Handler not implemented for command: {command}")
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
        num_chunks = math.ceil(size / self.LARGE_MESSAGE_LIMIT)
        block_bytes_read = 0
        tx_offsets_all: "array.ArrayType[int]" = array.array("Q")
        block_hash = bytes()
        adjustment = 0
        while block_bytes_read < size:
            stream.seek(0, os.SEEK_END)
            if (size - block_bytes_read) >= self.LARGE_MESSAGE_LIMIT:
                data = await self.reader.readexactly(self.LARGE_MESSAGE_LIMIT)
            else:
                data = await self.reader.readexactly(size - block_bytes_read)
            if not data:
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
            await self.message_handler.on_block_chunk(block_chunk_data, self.peer)

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
        await self.message_handler.on_block(block_data_msg, self.peer)

    async def send_version(self, local_host: str, local_port: int) -> None:
        message = self.serializer.version(
            recv_host=self.remote_host,
            recv_port=self.remote_port,
            send_host=local_host,
            send_port=local_port,
        )
        await self.send_message(message)

    async def handshake(self, local_host: str, local_port: int) -> None:
        create_task(self.send_version(local_host, local_port))
        await self.handshake_complete_event.wait()

    async def start_session(self) -> None:
        try:
            await self._session()
        except ConnectionResetError:
            self.logger.error(f"Bitcoin node disconnected")
        finally:
            if self.writer and not self.writer.is_closing():
                await self.close_connection()

    async def keepalive(self) -> None:
        await self.handshake_complete_event.wait()
        self.logger.debug(f"Handshake event complete")
        await asyncio.sleep(2)
        while True:
            ping_msg = self.serializer.ping()
            await self.send_message(ping_msg)
            await asyncio.sleep(2 * 60)  # Matches bitcoin-sv/net/net.h constant PING_INTERVAL
