import asyncio
import os
from io import BytesIO
import logging

from bitcoinx import Header, MissingHeader, hash_to_hex_str

from conduit_p2p import BitcoinClientManager, HandlersDefault
from conduit_p2p.client import BitcoinClient, get_max_headers, wait_for_new_tip_reorg_aware
from conduit_p2p.constants import TESTNET, REGTEST, MAINNET, ZERO_HASH
from conduit_p2p.deserializer import Inv
from conduit_p2p.headers import HeadersStore, NewTipResult
from conduit_p2p.types import BitcoinClientMode, InvType, BlockDataMsg, BlockChunkData
from conduit_p2p.utils import create_task

logging.basicConfig(format="%(asctime)-25s %(levelname)-10s %(name)-28s %(message)s")
logger = logging.getLogger("conduit.p2p.headers.example")
logger.setLevel(logging.DEBUG)


peers = {
    TESTNET: ["128.199.40.30:18333", "167.172.61.80:18333", "136.243.78.45:18333", "142.132.159.187:18333"],
    REGTEST: ["127.0.0.1:18444", "127.0.0.1:18444", "127.0.0.1:18444"],
    MAINNET: ["13.57.104.213:8333", "18.182.32.193:8333", "18.197.105.221:8333", "125.236.230.82:8333"]
}


class AppState:

    def __init__(self) -> None:
        self.new_headers_queue: asyncio.Queue[NewTipResult] = asyncio.Queue()


class IndexerHandlers(HandlersDefault):

    def __init__(self, network_type: str, app_state: AppState):
        super().__init__(network_type)
        self.app_state = app_state

    async def on_block_chunk(self, block_chunk_data: BlockChunkData, peer: BitcoinClient) -> None:
        """These block chunks are sized to the nearest whole transaction.
        This allows parallel processing. The transaction offsets are also provided for quick
        random access"""
        self.logger.debug("Received big block chunk number %s with block_hash: %s (peer_id=%s)",
            block_chunk_data.chunk_num, hash_to_hex_str(block_chunk_data.block_hash), peer.id)

    async def on_block(self, block_data_msg: BlockDataMsg, peer: BitcoinClient) -> None:
        """Small blocks are provided as one blob, whereas big blocks (exceeding LARGE_MESSAGE_LIMIT)
        are provided as chunks in the `on_block_chunk` callback."""

        block_hash = block_data_msg.block_hash
        # if block_data_msg.block_type == BlockType.SMALL_BLOCK:
        #     self.logger.debug("Received small block with block_hash: %s (peer_id=%s)",
        #         hash_to_hex_str(block_hash), peer.id)
        # else:
        #     self.logger.debug("Received all big block chunks for block_hash: %s (peer_id=%s)",
        #         hash_to_hex_str(block_hash), peer.id)

        if self.client_manager:
            self.client_manager.mark_block_done(block_hash)


async def headers_sync_task(client_manager: BitcoinClientManager, headers_store, app_state: AppState) -> None:
    # No need for reorg-awareness
    client = await client_manager.get_next_available_peer()
    while headers_store.tip().height < client.remote_start_height:
        message = await get_max_headers(client, headers_store)
        if message:
            headers_store.connect_headers(BytesIO(message))
            logger.info(f"New headers tip height: {headers_store.tip().height} "
                        f"(peer={client.id})")
        else:
            logger.debug(f"No headers returned (peer_id={client.id})")

    new_tip = NewTipResult(is_reorg=False, start_header=headers_store.get_header_for_height(0),
        stop_header=headers_store.tip(), old_chain=None, new_chain=None, reorg_info=None)
    logger.info(f"Finished initial headers download. "
                f"New tip: {new_tip.stop_header.height}")
    await app_state.new_headers_queue.put(new_tip)

    # Reorg-awareness necessary now
    async for new_tip in wait_for_new_tip_reorg_aware(client, headers_store):
        if not new_tip.is_reorg:
            logger.info(f"New headers tip height: %s (peer={client.id})", new_tip.stop_header.height)
        else:
            logger.debug(f"Reorg detected. Common parent height: {new_tip.reorg_info.commmon_height}. "
                         f"Old tip:{new_tip.reorg_info.old_tip}. "
                         f"New tip: {new_tip.reorg_info.new_tip}")
        await app_state.new_headers_queue.put(new_tip)


async def get_wanted_block_data(wanted: list[Header], client_manager: BitcoinClientManager,
        start_locator_hash: bytes, stop_locator_hash: bytes):
    """If a BitcoinClient disconnects at any time, the queued work for that client will be re-allocated"""
    # This allows calling getblocks for newly joined or reconnecting peers
    client_manager.wanted_blocks = set(x.hash for x in wanted)
    client_manager.wanted_block_first = wanted[0]
    client_manager.wanted_block_last = wanted[-1]

    # Get an inventory of which peers have which blocks available
    clients = client_manager.get_connected_peers()
    for client in clients:
        client.queued_getdata_requests = asyncio.Queue(maxsize=100)  # New queue
        message = client.serializer.getblocks(len([wanted[0].hash]),
            [start_locator_hash], stop_locator_hash)
        client.queued_getdata_requests.put_nowait(message)
        client.send_message(message)

    for header in wanted:
        not_tried_yet_count = len(client_manager.get_connected_peers())
        while True:
            if len(client_manager.get_connected_peers()) < 1:
                # logger.debug(f"No available connected peers. Waiting")
                await asyncio.sleep(10)
                continue

            client = await client_manager.get_next_available_peer()
            if header.hash in client.have_blocks and header.hash in client_manager.wanted_blocks:
                # logger.debug(f"Sending getdata for block height: {header.height} (peer_id={client.id})")
                message = client.serializer.getdata(
                    [Inv(inv_type=InvType.BLOCK, inv_hash=header.hex_str())])
                client.send_message(message)
                break
            else:
                logger.debug(f"Block {header.height} not found in peer: {client.id}")
                not_tried_yet_count -= 1
                if not_tried_yet_count == 0:
                    # When the blocks start getting bigger, it's probably
                    # worth sacrificing on a longer sleep here just so that
                    # all connected peers get sufficient time to respond with
                    # their inventory of available blocks.
                    await asyncio.sleep(0.5)
                    # Hopefully new connected peers which will immediately
                    # send a getblocks request to populate the `client.have_blocks`
                    not_tried_yet_count = len(client_manager.get_connected_peers())


async def blocks_sync_task(client_manager: BitcoinClientManager, headers_store: HeadersStore,
        headers_store_done_blocks: HeadersStore, app_state: AppState) -> None:
    logger.info(f"Starting from tip height: {headers_store_done_blocks.tip().height}")
    while True:
        if headers_store_done_blocks.tip().height == headers_store.tip().height:
            new_tip: NewTipResult = await app_state.new_headers_queue.get()
            try:
                # Two new chain tips in quick secession can do this
                headers_store_done_blocks.get_header_for_hash(new_tip.stop_header.hash)
                continue
            except MissingHeader:
                pass
            # Start & Stop locator block hashes (can start below local tip for a reorg)
            start_locator_hash = new_tip.start_header.hash
            stop_locator_hash = new_tip.stop_header.hash
            stop_height = headers_store.get_header_for_hash(stop_locator_hash).height
            start_height = max(headers_store.get_header_for_hash(start_locator_hash).height, 1)
        else:
            done_blocks_tip = headers_store_done_blocks.tip()
            start_locator_hash = headers_store.get_header_for_height(done_blocks_tip.height).hash
            remainder = headers_store.tip().height - done_blocks_tip.height
            allocation_count = min(500, remainder)
            stop_height = done_blocks_tip.height + allocation_count
            if stop_height >= headers_store.tip().height:
                stop_locator_hash = ZERO_HASH
            else:
                stop_locator_hash = headers_store.get_header_for_height(stop_height + 1).hash
            start_height = done_blocks_tip.height + 1
            if start_height <= 0:
                start_height = 1

        wanted: list[Header] = [headers_store.get_header_for_height(height) for height in
            range(start_height, stop_height + 1)]

        await get_wanted_block_data(wanted, client_manager, start_locator_hash, stop_locator_hash)

        # The raw block data will flow asynchronously into the on_block & on_block_chunk handlers now

        while len(client_manager.wanted_blocks) > 0:
            logger.debug(f"Waiting for {len(client_manager.wanted_blocks)} blocks to be processed...")
            logger.info(f"Connected peers: {len(client_manager.get_connected_peers())}")
            logger.info(f"Disconnected peers: {len(client_manager._disconnected_pool)}")
            await asyncio.sleep(1)

        # Connect to done block headers store only when all of them are complete
        for header in wanted:
            headers_store_done_blocks.headers.connect(header.raw, check_work=False)
        headers_store_done_blocks.write_cached_headers()

        logger.info(f"New tip height: {headers_store_done_blocks.tip().height}")
        client_manager.wanted_blocks = set()


async def main():
    # Config
    os.environ['NETWORK'] = TESTNET

    # State & Persistence
    app_state = AppState()
    network = os.getenv('NETWORK', TESTNET)
    headers_store = HeadersStore(f"headers.{network}", network)
    headers_store_done_blocks = HeadersStore(f"headers.blocks.{network}", network)

    # Connect to peers
    message_handler = IndexerHandlers(network, app_state)
    peers_list = peers[network]
    async with BitcoinClientManager(message_handler, peers_list,
            mode=BitcoinClientMode.HIGH_LEVEL, relay_transactions=False,
            use_persisted_peers=True, start_height=headers_store_done_blocks.tip().height,
            concurrency=3
    ) as client_manager:

        # Download all headers to chain tip
        create_task(headers_sync_task(client_manager, headers_store, app_state))

        # Download all blocks to catch up to the local chain tip
        #     - headers_store               for headers only
        #     - headers_store_done_blocks   for marking blocks completed
        create_task(blocks_sync_task(client_manager, headers_store, headers_store_done_blocks, app_state))

        await client_manager.listen()


try:
    asyncio.run(main())
except KeyboardInterrupt:
    logger.debug(f"Program stopped")
