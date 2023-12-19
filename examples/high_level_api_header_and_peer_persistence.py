import asyncio
from io import BytesIO
import logging

from conduit_p2p import BitcoinClientManager, HandlersDefault
from conduit_p2p.client import get_max_headers, wait_for_new_tip_reorg_aware
from conduit_p2p.constants import TESTNET, REGTEST, MAINNET
from conduit_p2p.headers import HeadersStore
from conduit_p2p.types import BitcoinClientMode

logging.basicConfig(format="%(asctime)-25s %(levelname)-10s %(name)-28s %(message)s")
logger = logging.getLogger("conduit.p2p.headers.example")
logger.setLevel(logging.DEBUG)


peers = {
    TESTNET: ["136.243.78.45:18333", "142.132.159.187:18333", "128.199.40.30:18333"],
    REGTEST: ["127.0.0.1:18444", "127.0.0.1:18444", "127.0.0.1:18444"],
    MAINNET: ["13.57.104.213:8333", "18.182.32.193:8333", "18.197.105.221:8333", "125.236.230.82:8333"]
}


async def main():
    network = TESTNET
    headers_store = HeadersStore(f"headers.{network}", network)

    # Connect to testnet peers and download all headers to chain tip
    message_handler = HandlersDefault(network)
    peers_list = peers[network]

    # If there is no intention to listen to the mempool, set relay_transactions=False
    async with BitcoinClientManager(message_handler, peers_list,
            mode=BitcoinClientMode.HIGH_LEVEL, relay_transactions=False,
            use_persisted_peers=True, start_height=headers_store.tip().height) as client_manager:
        client = await client_manager.get_next_available_peer()

        while headers_store.tip().height < client.remote_start_height:
            message = await get_max_headers(client, headers_store)
            if message:
                headers_store.connect_headers(BytesIO(message))
                logger.info(f"New headers tip height: {headers_store.tip().height} "
                            f"(peer={client.id})")
            else:
                logger.debug(f"No headers returned (peer_id={client.id})")

        logger.info(f"Finished initial headers download. Waiting for new chain tip")
        async for new_tip in wait_for_new_tip_reorg_aware(client, headers_store):
            if not new_tip.is_reorg:
                logger.info(f"New headers tip height: %s (peer={client.id})", new_tip.stop_header.height)
            else:
                logger.debug(f"Reorg detected. Common parent height: {new_tip.reorg_info.commmon_height}. "
                             f"Old tip:{new_tip.reorg_info.old_tip}. "
                             f"New tip: {new_tip.reorg_info.new_tip}")

try:
    asyncio.run(main())
except KeyboardInterrupt:
    logger.debug(f"Program stopped")
