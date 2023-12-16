# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

import asyncio
import bitcoinx
from bitcoinx import double_sha256, hash_to_hex_str, pack_varint, hex_str_to_hash
import io
import unittest
from math import ceil
from pathlib import Path
from typing import cast, Coroutine, Any, TypeVar
import unittest.mock
import electrumsv_node
import pytest
import logging
import os

from conduit_p2p.preprocessor import unpack_varint
from conduit_p2p.client_manager import BitcoinClientManager
from conduit_p2p.types import (
    BlockChunkData,
    BlockDataMsg,
    BlockType,
)
from conduit_p2p.commands import BLOCK_BIN, BLOCK
from conduit_p2p.constants import REGTEST, ZERO_HASH
from conduit_p2p import commands
from conduit_p2p.handlers import HandlersDefault
from conduit_p2p import (
    BitcoinClient,
    NetworkConfig,
    Serializer,
)
from scripts.import_blocks import import_blocks

from .data.big_data_carrier_tx import DATA_CARRIER_TX

MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
os.environ["GENESIS_ACTIVATION_HEIGHT"] = "0"
os.environ["NETWORK_BUFFER_SIZE"] = "1000000"

logger = logging.getLogger("bitcoin-p2p-socket")
logger.setLevel(logging.DEBUG)

REGTEST_NODE_HOST = "127.0.0.1"
REGTEST_NODE_PORT = 18444


T1 = TypeVar("T1")


def asyncio_future_callback_raise_exception(future: asyncio.Task[Any]) -> None:
    if future.cancelled():
        return
    try:
        future.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception(f"Unexpected exception in task")
        raise


def create_task(coro: Coroutine[Any, Any, T1]) -> asyncio.Task[T1]:
    task = asyncio.create_task(coro)
    # Futures catch all exceptions that are raised and store them. A task is a future. By adding
    # this callback we reraise any encountered exception in the callback and ensure it is visible.
    task.add_done_callback(asyncio_future_callback_raise_exception)
    return task


class MockHandlers(HandlersDefault):
    """The intent here is to make assertions that the appropriate handlers are being called and in
    the right way.

    `received_message_queue` would not be a part of this handler class under normal circumstances
    """

    def __init__(self, network_type: str, received_message_queue: asyncio.Queue) -> None:
        super().__init__(network_type=network_type)
        self.logger.setLevel(logging.WARNING)
        self.received_message_queue = received_message_queue
        self.getdata_txs_all = True
        self.getdata_blocks_all = True

    async def on_version(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_version(message, peer)
        self.received_message_queue.put_nowait((commands.VERSION, message, peer))

    async def on_verack(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_verack(message, peer)
        self.received_message_queue.put_nowait((commands.VERACK, message, peer))

    async def on_protoconf(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_protoconf(message, peer)
        self.received_message_queue.put_nowait((commands.PROTOCONF, message, peer))

    async def on_sendheaders(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_sendheaders(message, peer)
        self.received_message_queue.put_nowait((commands.SENDHEADERS, message, peer))

    async def on_sendcmpct(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_sendcmpct(message, peer)
        self.received_message_queue.put_nowait((commands.SENDCMPCT, message, peer))

    async def on_ping(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_ping(message, peer)
        self.received_message_queue.put_nowait((commands.PING, message, peer))

    async def on_pong(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_pong(message, peer)
        self.received_message_queue.put_nowait((commands.PONG, message, peer))

    async def on_addr(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_addr(message, peer)
        self.received_message_queue.put_nowait((commands.ADDR, message, peer))

    async def on_feefilter(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_feefilter(message, peer)
        self.received_message_queue.put_nowait((commands.FEEFILTER, message, peer))

    async def on_authch(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_authch(message, peer)
        self.received_message_queue.put_nowait((commands.AUTHCH, message, peer))

    async def on_inv(self, message: bytes, peer: BitcoinClient,
            getdata_txs_all: bool = False, getdata_blocks_all: bool = False) -> None:
        await super().on_inv(message, peer)
        self.received_message_queue.put_nowait((commands.INV, message, peer))

    async def on_getdata(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_getdata(message, peer)
        self.received_message_queue.put_nowait((commands.GETDATA, message, peer))

    async def on_headers(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_headers(message, peer)
        self.received_message_queue.put_nowait((commands.HEADERS, message, peer))

    async def on_tx(self, message: bytes, peer: BitcoinClient) -> None:
        await super().on_tx(message, peer)
        self.received_message_queue.put_nowait((commands.TX, message, peer))

    async def on_block_chunk(self, block_chunk_data: BlockChunkData, peer: BitcoinClient) -> None:
        await super().on_block_chunk(block_chunk_data, peer)
        self.received_message_queue.put_nowait((commands.BLOCK, block_chunk_data, peer))

    async def on_block(self, block_data_msg: BlockDataMsg, peer: BitcoinClient) -> None:
        await super().on_block(block_data_msg, peer)
        self.received_message_queue.put_nowait((commands.BLOCK, block_data_msg, peer))


async def _drain_handshake_messages(client: BitcoinClient, message_handler: MockHandlers,
        expected_message_commands: set[str]):
    while True:
        try:
            item = message_handler.received_message_queue.get_nowait()
            command, message, peer = item
            expected_message_commands.remove(command)
        except asyncio.QueueEmpty:
            logger.debug(f"Still expecting these message types: {expected_message_commands}")
            await asyncio.sleep(2)

        if not expected_message_commands:
            break
    assert len(expected_message_commands) == 0
    assert client.handshake_complete_event.is_set()


def setup_module(module) -> None:
    blockchain_dir = MODULE_DIR.parent / "contrib" / "blockchains" / "blockchain_116_7c9cd2"
    import_blocks(str(blockchain_dir))
    # time.sleep(5)


@pytest.mark.timeout(30)
@pytest.mark.asyncio
async def test_handshake() -> None:
    client = None
    try:
        received_message_queue = asyncio.Queue()
        message_handler = MockHandlers(REGTEST, received_message_queue)
        client = BitcoinClient(1, REGTEST_NODE_HOST, REGTEST_NODE_PORT, message_handler)
        await client.connect()

        expected_message_commands = {
            commands.VERSION,
            commands.VERACK,
            commands.PING,
            commands.PONG,
            commands.PROTOCONF,
            commands.SENDHEADERS,
            commands.SENDCMPCT,
            commands.AUTHCH
        }
        for i in range(len(expected_message_commands)):
            command, message, peer = await message_handler.received_message_queue.get()
            expected_message_commands.remove(command)
        assert len(expected_message_commands) == 0
        assert client.handshake_complete_event.is_set()
    finally:
        if client:
            await client.close()


@pytest.mark.asyncio
async def test_getheaders_request_and_headers_response() -> None:
    # Otherwise the node might still be in initial block download mode (ignores header requests)
    electrumsv_node.call_any("generate", 1)

    client = None
    try:
        received_message_queue = asyncio.Queue()
        message_handler = MockHandlers(REGTEST, received_message_queue)
        client = BitcoinClient(1, REGTEST_NODE_HOST, REGTEST_NODE_PORT, message_handler)
        await client.connect()

        expected_message_commands = {
            commands.VERSION,
            commands.VERACK,
            commands.PING,
            commands.PONG,
            commands.PROTOCONF,
            commands.SENDHEADERS,
            commands.SENDCMPCT,
            commands.AUTHCH
        }
        await _drain_handshake_messages(client, message_handler, expected_message_commands)

        message = client.serializer.getheaders(1, block_locator_hashes=[ZERO_HASH], hash_stop=ZERO_HASH)
        client.send_message(message)

        command, message, peer = await message_handler.received_message_queue.get()
        headers = client.deserializer.headers(io.BytesIO(message))
        node_rpc_result = electrumsv_node.call_any("getinfo").json()["result"]
        height = node_rpc_result["blocks"]
        assert len(headers) == height
        headers_count, offset = unpack_varint(message, 0)
        assert headers_count == len(headers)
    finally:
        if client:
            await client.close()


@pytest.mark.asyncio
async def test_peer_manager():
    # Otherwise the node might still be in initial block download mode (ignores header requests)
    electrumsv_node.call_any('generate', 1)

    peer_manager = None
    try:
        received_message_queue = asyncio.Queue()
        message_handler = MockHandlers(REGTEST, received_message_queue)
        peers_list = ["127.0.0.1:18444", "127.0.0.1:18444", "127.0.0.1:18444"]
        peer_manager = BitcoinClientManager(message_handler, peers_list=peers_list)
        await peer_manager.connect_all_peers()
        assert len(peer_manager.get_connected_peers()) == len(peer_manager.clients) == 3

        # No index out of range
        client_ids = []
        for i in range(6):
            client = peer_manager.get_current_peer()
            client_ids.append(client.id)
            peer_manager.select_next_peer()
        assert client_ids == [1, 2, 3, 1, 2, 3]
        assert len(peer_manager.get_connected_peers()) == 3

        locator_hashes = [
            hash_to_hex_str(ZERO_HASH),
            "6183377618699384b4409f0906d3f15413f29ce1b9951e4eab99570d3f8ba7c0",  # height=10
            "4ee607aadb468f44c9b82dffb0d8741112c10f0249be6d592b8a19579e414a07",  # height=20
        ]

        expected_message_commands = {
            commands.VERSION,
            commands.VERACK,
            commands.PING,
            commands.PONG,
            commands.PROTOCONF,
            commands.SENDHEADERS,
            commands.SENDCMPCT,
            commands.AUTHCH
        }
        peer_map = {
            1: expected_message_commands.copy(),
            2: expected_message_commands.copy(),
            3: expected_message_commands.copy()
        }
        for i in range(3*len(expected_message_commands)):
            command, message, peer = await message_handler.received_message_queue.get()
            if command == 'version':
                logger.debug(f"peer_id: {peer.id}")
            peer_map[peer.id].remove(command)
        assert len(peer_map[1]) == 0 and len(peer_map[2]) == 0 and len(peer_map[3]) == 0

        for i in range(len(peer_manager.clients)):
            peer_manager.select_next_peer()
            client = peer_manager.get_current_peer()
            message = client.serializer.getheaders(
                1, block_locator_hashes=[hex_str_to_hash(locator_hashes[0])], hash_stop=ZERO_HASH
            )
            client.send_message(message)
            command, message, peer = await message_handler.received_message_queue.get()
            headers = client.deserializer.headers(io.BytesIO(message))
            node_rpc_result = electrumsv_node.call_any('getinfo').json()['result']
            height = node_rpc_result['blocks']
            assert len(headers) == height
            headers_count, offset = unpack_varint(message, 0)
            assert headers_count == len(headers)
    finally:
        if peer_manager:
            await peer_manager.close()


@pytest.mark.asyncio
async def test_getblocks_request_and_blocks_response():
    client = None
    try:
        received_message_queue = asyncio.Queue()
        message_handler = MockHandlers(REGTEST, received_message_queue)
        client = BitcoinClient(
            1,
            REGTEST_NODE_HOST,
            REGTEST_NODE_PORT,
            message_handler,
        )
        await client.connect()

        expected_message_commands = {
            commands.VERSION,
            commands.VERACK,
            commands.PING,
            commands.PONG,
            commands.PROTOCONF,
            commands.SENDHEADERS,
            commands.SENDCMPCT,
            commands.AUTHCH,
        }
        await _drain_handshake_messages(client, message_handler, expected_message_commands)

        message = client.serializer.getblocks(1, block_locator_hashes=[ZERO_HASH], hash_stop=ZERO_HASH)
        client.send_message(message)


        node_rpc_result = electrumsv_node.call_any("getinfo").json()["result"]
        height = node_rpc_result["blocks"]

        count_blocks_received = 0
        count_blocks_expected = height
        while True:
            command, message, peer = await message_handler.received_message_queue.get()
            if command != BLOCK:
                continue
            count_blocks_received += 1
            logger.debug(f"Got block message number: {count_blocks_received}")
            message = cast(BlockDataMsg, message)
            raw_header = message.small_block_data[0:80]
            block_hash = double_sha256(raw_header)
            # node_rpc_result = electrumsv_node.call_any("getblock", hash_to_hex_str(block_hash)).json()[
            #     "result"
            # ]
            header, block_txs = client.deserializer.block(io.BytesIO(message.small_block_data))
            # assert node_rpc_result["num_tx"] == len(block_txs)
            txs_count, offset = unpack_varint(message.small_block_data[80:89], 0)
            assert txs_count == len(block_txs)
            if count_blocks_expected == count_blocks_received:
                break
    finally:
        if client:
            await client.close()


def _parse_txs_with_bitcoinx(message: BlockChunkData) -> None:
    correct_tx_hash = bitcoinx.double_sha256(bytes.fromhex(DATA_CARRIER_TX))
    size_data_carrier_tx = len(bytes.fromhex(DATA_CARRIER_TX))
    normalizer = 0
    if message.chunk_num != 1:
        normalizer = message.tx_offsets_for_chunk[0]
    for i in range(len(message.tx_offsets_for_chunk)):
        if i < len(message.tx_offsets_for_chunk) - 1:
            offset_start = message.tx_offsets_for_chunk[i] - normalizer
            offset_end = message.tx_offsets_for_chunk[i + 1] - normalizer
            tx = bitcoinx.Tx.from_bytes(message.raw_block_chunk[offset_start:offset_end])
        else:
            offset_start = message.tx_offsets_for_chunk[i] - normalizer
            tx = bitcoinx.Tx.from_bytes(message.raw_block_chunk[offset_start:])
        print(len(tx.to_bytes()))
        assert len(tx.to_bytes()) == size_data_carrier_tx
        assert tx.hash() == correct_tx_hash


@pytest.mark.asyncio
async def test_big_block_exceeding_network_buffer_capacity() -> None:
    client = None
    task = None
    try:
        net_config = NetworkConfig(REGTEST)
        serializer = Serializer(net_config)
        fake_header_block_116 = bytes.fromhex("000000201b94e4366e4d283d1cd3834aed03b4fd0be15fcc6ab4e387df04f08ddff47736bc86ff7435135f70a33a9105551b0ea7719b9fb2c0a7e882976b3b977985adab2189f461ffff7f2001000000")
        block_hash = double_sha256(fake_header_block_116)
        logger.debug(f"Expected block_hash: {hash_to_hex_str(block_hash)}")
        size_data_carrier_tx = len(bytes.fromhex(DATA_CARRIER_TX))
        big_block = bytearray(fake_header_block_116)
        tx_count_to_exceed_buffer = ceil(1000000 / size_data_carrier_tx)
        big_block += pack_varint(tx_count_to_exceed_buffer)
        for i in range(tx_count_to_exceed_buffer):
            big_block += bytes.fromhex(DATA_CARRIER_TX)

        message_to_send = serializer.payload_to_message(BLOCK_BIN, big_block)
        received_message_queue = asyncio.Queue()

        message_handler = MockHandlers(REGTEST, received_message_queue)

        reader = asyncio.StreamReader()
        writer = unittest.mock.Mock()
        client = BitcoinClient(
            1,
            REGTEST_NODE_HOST,
            REGTEST_NODE_PORT,
            message_handler,
            reader=reader,
            writer=writer,
        )
        client.large_message_limit = 500000
        client.reader.feed_data(message_to_send)
        client.peer = unittest.mock.Mock()

        task = create_task(client.start_session())
        expected_msg_count = 4  # 2 x BlockChunkData; 1 x BlockDataMsg for the full block
        msg_count = 0
        for i in range(expected_msg_count):
            command, message, peer = await message_handler.received_message_queue.get()
            msg_count += 1
            logger.debug(f"Got '{command}' message_type: {type(message)}")
            if msg_count == 1:
                assert isinstance(message, BlockChunkData)
                assert message.chunk_num == 1
                assert message.num_chunks == 3
                assert message.block_hash == block_hash
                assert len(message.raw_block_chunk) == 460317
                assert message.tx_offsets_for_chunk.tolist() == [
                    81,
                    65829,
                    131577,
                    197325,
                    263073,
                    328821,
                    394569,
                ]

                _parse_txs_with_bitcoinx(message)

            if msg_count == 2:
                assert isinstance(message, BlockChunkData)
                assert message.chunk_num == 2
                assert message.num_chunks == 3
                assert message.block_hash == block_hash

                # This chunk should be 525984 bytes due to the remainder of the previous chunk
                assert len(message.raw_block_chunk) == (986301 - 460317)
                assert message.tx_offsets_for_chunk.tolist() == [
                    460317,
                    526065,
                    591813,
                    657561,
                    723309,
                    789057,
                    854805,
                    920553,
                ]

                _parse_txs_with_bitcoinx(message)

            if msg_count == 3:
                assert isinstance(message, BlockChunkData)
                assert message.chunk_num == 3
                assert message.num_chunks == 3
                assert message.block_hash == block_hash
                assert len(message.raw_block_chunk) == 65748
                assert message.tx_offsets_for_chunk.tolist() == [986301]

                _parse_txs_with_bitcoinx(message)

            if msg_count == 4:
                assert isinstance(message, BlockDataMsg)
                assert message.block_type == BlockType.BIG_BLOCK
                assert message.block_hash == block_hash
                assert message.tx_offsets.tolist() == [
                    81,
                    65829,
                    131577,
                    197325,
                    263073,
                    328821,
                    394569,
                    460317,
                    526065,
                    591813,
                    657561,
                    723309,
                    789057,
                    854805,
                    920553,
                    986301,
                ]
                assert message.block_size == 1052049
                assert message.small_block_data == None
                assert message.block_size == len(big_block)
    finally:
        if task:
            try:
                # Raise any exceptions in this thread otherwise timeout and pass
                await asyncio.wait_for(task, timeout=3.0)
            except asyncio.TimeoutError:
                pass
        if client:
            await client.close()
