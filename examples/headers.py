import asyncio
import io
import json
import logging

import requests
from bitcoinx import hex_str_to_hash, hash_to_hex_str

from conduit_p2p import BitcoinClient, NetworkConfig
from conduit_p2p.client_manager import BitcoinClientManager
from conduit_p2p.constants import REGTEST, ZERO_HASH
from conduit_p2p.handlers import HandlersDefault
from conduit_p2p.types import BitcoinPeerInstance

REGTEST_NODE_HOST = "127.0.0.1"
REGTEST_NODE_PORT = 18444


def call_rpc(method_name: str, *args, rpcport: int=18332, rpchost: str="127.0.0.1", rpcuser:
        str="rpcuser", rpcpassword: str="rpcpassword"):
    """Send an RPC request to the specified bitcoin node"""
    result = None
    try:
        if not args:
            params = []
        else:
            params = [*args]
        payload = json.dumps(
            {"jsonrpc": "2.0", "method": f"{method_name}", "params": params, "id": 0})
        result = requests.post(f"http://{rpcuser}:{rpcpassword}@{rpchost}:{rpcport}", data=payload,
                               timeout=10.0)
        result.raise_for_status()
        return result
    except requests.exceptions.HTTPError as e:
        if result is not None:
            print(result.json()['error']['message'])
        raise e


class MyApplicationHandlers(HandlersDefault):
    """There is no need to implement the other callbacks if you do not wish to"""

    def __init__(self, net_config: NetworkConfig):
        super().__init__(net_config)

    async def on_headers(self, message: bytes, peer: BitcoinPeerInstance) -> None:
        headers = self.deserializer.headers(io.BytesIO(message))
        self.logger.debug("Received headers (peer_id=%s)", peer.peer_id)
        for header in headers:
            self.logger.debug(f"header: {header}")


async def main():
    logging.basicConfig(format="%(asctime)-25s %(levelname)-10s %(name)-28s %(message)s", level=logging.DEBUG)
    call_rpc('generate', 1, rpcport=18332)
    net_config = NetworkConfig(REGTEST, REGTEST_NODE_HOST, REGTEST_NODE_PORT)
    message_handler = MyApplicationHandlers(net_config)

    # Generate three, concurrent connections to the same localhost regtest node
    client = BitcoinClient(1, REGTEST_NODE_HOST, REGTEST_NODE_PORT, message_handler, net_config)
    client2 = BitcoinClient(2, REGTEST_NODE_HOST, REGTEST_NODE_PORT, message_handler, net_config)
    client3 = BitcoinClient(3, REGTEST_NODE_HOST, REGTEST_NODE_PORT, message_handler, net_config)
    peer_manager = BitcoinClientManager(clients=[client, client2, client3])
    await peer_manager.try_connect_to_all_peers()
    await asyncio.sleep(2)

    locator_hashes = [
        hash_to_hex_str(ZERO_HASH),
        "6183377618699384b4409f0906d3f15413f29ce1b9951e4eab99570d3f8ba7c0",  # height=10
        "4ee607aadb468f44c9b82dffb0d8741112c10f0249be6d592b8a19579e414a07",  # height=20
    ]
    client = peer_manager.get_next_peer()
    message = client.serializer.getheaders(
        1, block_locator_hashes=[hex_str_to_hash(locator_hashes[0])], hash_stop=ZERO_HASH
    )
    await client.send_message(message)

    await asyncio.sleep(10)
    await peer_manager.close()

asyncio.run(main())
