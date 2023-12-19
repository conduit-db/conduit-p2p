# ConduitP2P

**ConduitP2P** is a library for connecting to the BitcoinSV p2p network and is targeted at two primary use cases:

- For services that index or filter the entire blockchain (https://github.com/conduit-db/conduit-db)
- SPV wallets/apps connecting directly to the p2p network for header acquisition and/or transaction broadcasting

It aims to be as simple as possible without needlessly sacrificing performance for the indexer use case.

<table>
  <tr>
    <td><b>Licence</b></td>
    <td>MIT</td>
  </tr>
  <tr>
    <td><b>Language</b></td>
    <td>Python 3.10</td>
  </tr>
  <tr>
    <td><b>Author</b></td>
    <td>Hayden Donnelly (AustEcon)</td>
  </tr>
</table>

# Design Overview & Usage
The API is based around handlers / callbacks because this is how the p2p network was fundamentally 
designed - a high throughput, asynchronous relay network.

The constructor of the example `SPVApplicationHandlers` below is where you could add significant application state
to push messages into queues, write to files or databases, trigger events, route messages to worker
processes for parsing, update a redis cache etc. 

There is a single instance of the `SPVApplicationHandlers` which is shared by all `BitcoinClient` connections. Within
each handler, you can access both:

- The `BitcoinClient` that made the original request
- The higher-order,`BitcoinClientManager` that manages all `BitcoinClient` connections and handles 
disconnects/re-connections. 

See the `examples/` directory at the root of this git repo.

## Installing ConduitP2P and Supported Versions

ConduitP2P is available on PyPI & supports python versions 3.9+:

```console
$ python -m pip install conduit-p2p
```

## High level API
The high level API (i.e. `mode=BitcoinClientMode.HIGH_LEVEL`) uses 
internal queues which redirect messages from the handlers.
This is able to give a request/response 'feel' in many ways.

It also unlocks the usage of helper functions:

- `BitcoinClient.broadcast_transaction`  # Returns rejections
- `BitcoinClientManager.broadcast_transaction_and_listen`  # Returns rejections AND peer ids relaying the tx back
- `BitcoinClient.get_headers`  # Returns a p2p message format header message for deserializing

### Example: Reorg-aware headers acquisition & persistence (& peer info persistence).
This is the most "high-level" of abstraction example because it uses two heavy-weight,
opt-in features:
- The thread-safe & reorg-aware headers store
- Peer info persistence to .json file

The persistent headers store will detect reorgs when connecting to the new chain tip. 
If you're writing a chain indexer it is critical to be aware of reorg events to ensure 
the state of your database and mempool remains correct at all times.

This example below will:
    1) Connect to multiple peers for the preferred network
    2) Will read peers from the peers.<network>.json file and persist new peers not found 
       there yet. Will skip connecting to peers marked as `banned=true` in the .json file.
    3) Will get the next available peer (i.e. completed handshake and is ready to accept 
       getdata or getheaders messages)
    4) Will synchronize and persist all headers from the remote peer and then stay
       synchronized with the chain tip by waiting for new `inv` messages.
    NOTE: `relay_transactions=False` means that mempool transactions will not be relayed
    via `inv` messages. It's a good idea to do this to filter out mempool network chatter 
    if you are only wanting headers or raw blocks.

```python
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
```

### High level transaction broadcast & headers acquisition
This is the high level API without any headers or peer persistence which are both opt-in features.

The high-level `broadcast_transaction_and_listen` helper function used here will broadcast to a
single peer and listen for `inv` notifications from the other peers.

`concurrency=3` will open 3 connections per peer in the peers_list below. This is mostly only
useful for chain indexing functions where you want to add concurrency to getdata requests for 
blocks or transactions to overcome latency effects over a high-ping connection. It probably
doesn't add much for transaction broadcast unless you're doing high volumes (i.e. >1000txs/sec).

```python

async def main():
    logger = logging.getLogger('main')
    logger.setLevel(logging.DEBUG)
    message_handler = HandlersDefault(REGTEST)
    peers_list = ["127.0.0.1:18444"]

    async with BitcoinClientManager(message_handler, peers_list,
            mode=BitcoinClientMode.HIGH_LEVEL, concurrency=3) as client_manager:

        # REJECT_MALFORMED
        rawtx: bytes = b"raw transaction goes here"
        result: BroadcastResult = await client_manager.broadcast_transaction_and_listen(rawtx,
            broadcast_peer_count=1)
        if result.rejected is not None:
            logger.error(f"Transaction rejected. Reason: {result.rejected}")
        else:
            logger.error(f"Transaction accepted. Relaying peer_ids: {result.relaying_peer_ids}")

        # REJECT_NONSTANDARD
        rawtx: bytes = bytes.fromhex("020000000217de77d1421d6a6fff4a752524a9b810de8f407a8d833ed7b58f9843efe25853000000006b483045022100ed004a135f1ba01cf163beaff04662fc821581ac8ffeb3e1852e5ebdea82ab5d022052f0c8281c7f934d36667ba0770762228708d6b7e0bcd5463a777276080b9728412103f81d6e9176b7dfe9e86728d3b721ffd5ab9bdb9327be80b6824b8fd35cad96e3feffffff62f233fd8668e4722244279ccc1c94dc809f3cedca7e384795f7ba7e1f69e3df010000006b4830450221008e65c2867f7f4e5675242ba00eaaf98d21b338932c5574568f37b68ec438a82302205c1269ba81e53ea9f3755935e40813c62c9eaeb312888dd9b4b9f1a97d443198412103623a72e6962ccdd1e0793f87ca0af381e190a8857753b4c0cd3641160c5af2acfeffffff0350da1100000000001976a9149fe7cf03a32c8aa2dd684cb6ac697dc6495c6a7d88ac17131900000000001976a9142aa576137000b3e6e1ecb319657663df1a24982588acc0354e02000000001976a91400327f03b93172a7df917639cc5fb3e01822e93d88ac9c3b1800")
        result: BroadcastResult = await client_manager.broadcast_transaction_and_listen(rawtx,
            broadcast_peer_count=1)
        if result.rejected is not None:
            logger.error(f"Transaction rejected. Reason: {result.rejected}")
        else:
            logger.error(f"Transaction accepted. Relaying peer_ids: {result.relaying_peer_ids}")

        # This get_headers method requires use_headers_queue=True
        client = await client_manager.get_next_available_peer()
        message = await client.get_headers(
            hash_count=1,
            block_locator_hashes=[ZERO_HASH],
            hash_stop=ZERO_HASH
        )
        headers = client.deserializer.headers(BytesIO(message))
        for header in headers:
            logger.debug(f"Got header. Hash: {hash_to_hex_str(header.hash)}")

        logger.debug(f"Waiting for the new chain tip")
        while True:
            inv_vect = await client.inv_queue_blocks.get()
            logger.debug(f"Got inv_vect: {inv_vect}")

asyncio.run(main())
```


### Low-level API
The advanced API (i.e. `mode=BitcoinClientMode.LOW_LEVEL`) turns off
any "magic" helper functionality and expects you to over-ride the
relevant default handlers for your use case. Basically all the
default handlers except for the essential ones for completing the initial
connection handshake (version, verack) and staying connected (ping, pong) 
will just deserialize the message and log to console that they received it.

To get anything useful done, you'll need to override the handlers and write
your own custom business logic. However, the BitcoinClientMode.HIGH_LEVEL 
code in each default handler might serve as a template for your own 
implementation.

These functions will raise a ValueError if you try to use them in 
`mode=BitcoinClientMode.LOW_LEVEL`:

- `BitcoinClient.broadcast_transaction`
- `BitcoinClientManager.broadcast_transaction_and_listen`
- `BitcoinClient.get_headers`

In low-level mode, every message type follows the same pattern of
serializing the message & then sending.

```python
import asyncio
from io import BytesIO
import logging

from bitcoinx import hash_to_hex_str

from conduit_p2p import BitcoinClient, REGTEST, HandlersDefault, BitcoinClientManager, BitcoinClientMode
from conduit_p2p.constants import ZERO_HASH
from conduit_p2p.types import BlockHeader

logging.basicConfig(format="%(asctime)-25s %(levelname)-10s %(name)-28s %(message)s")


class SPVApplicationHandlers(HandlersDefault):
    """Override the other callbacks as you need to"""

    def __init__(self, network_type: str, app_state: dict[Any, Any]):
        super().__init__(network_type)
        self.logger.setLevel(logging.DEBUG)  # To silence the logs from the default handlers, set a higher level
        self.app_state = app_state

    async def on_headers(self, message: bytes, peer: BitcoinClient) -> None:
        if message[0:1] != b"\x00":  # Count of headers was zero
            headers: list[BlockHeader] = peer.deserializer.headers(BytesIO(message))
            for header in headers:
                self.logger.debug(f"Got header. Hash: {hash_to_hex_str(header.hash)}")

    async def on_inv(self, message: bytes, peer: BitcoinClient) -> None:
        inv_vect = peer.deserializer.inv(BytesIO(message))
        self.logger.debug("Received inv: %s (peer_id=%s)", inv_vect, peer.id)

    async def on_reject(self, message: bytes, peer: BitcoinClient) -> None:
        reject_msg = peer.deserializer.reject(BytesIO(message))
        self.logger.debug("Received reject: %s (peer_id=%s)", reject_msg, peer.id)


async def main():
    app_state = {}
    message_handler = SPVApplicationHandlers(REGTEST, app_state)
    peers_list = ["127.0.0.1:18444", "127.0.0.1:18444", "127.0.0.1:18444"]
    async with BitcoinClientManager(message_handler, peers_list, mode=BitcoinClientMode.LOW_LEVEL) as client_manager:
        rawtx: bytes = b"raw transaction goes here"
        client = await client_manager.get_next_available_peer()
        message = client.serializer.tx(rawtx)
        client.send_message(message)

        message = client.serializer.getheaders(
            hash_count=1,
            block_locator_hashes=[ZERO_HASH],
            hash_stop=ZERO_HASH
        )
        client.send_message(message)
        await client.listen()


asyncio.run(main())


```

# Specialized Block Handling
For the indexer use case, there are specialised handlers for raw blocks to avoid allocating 4GB blocks into memory:
- on_block
- on_block_chunk

Imagine you are indexing the chain and have 10+ peers connected and you try to concurrently load 10 x 4GB blocks into
memory at one time! Instead we should process large blocks in bite-sized chunks.

If the total size of the raw block is less than `large_message_limit` bytes (defaults to 32MB) then the `on_block`
handler is called with `BlockType.SMALL_BLOCK`, with the full raw block as a single blob (allocated into memory).

If the raw block is greater than or equal to `large_message_limit` bytes then `on_block_chunk` is called for every
32MB chunk sized to the nearest whole raw transaction. 

NOTE: The chunk sizes can actually be slightly larger than 32MB because it needs to splice together the remaining 
partial transaction bytes onto the next 32MB read. This is especially so if there is a very large transaction at 
the chunk boundary. The 32MB limit only determines when the chunking algorithm kicks in, it does not set a hard 
limit on the final chunk sizes but generally speaking it will be close to 32MB. The block_hash, chunk number, 
total number of chunks to be expected and transaction byte offsets are all included with each chunk. This provides 
all that is needed for parallel processing of large blocks.

Finally `on_block` is called with `BlockType.LARGE_BLOCK`. No raw block data is included when the block type is
`BlockType.LARGE_BLOCK` because it should have been processed elsewhere. This call is more of a formality that
might be used by your application to sign off on this part of the processing as being done or to include logic
that is common to both small and large block processing.

## Preprocessor
There is a transaction preprocessor which quickly skips through the raw block stream as it is read from the socket
and finds the starting byte offset in the raw block. This is useful for parallel processing on multiple workers.
This is what gives the ability to size each "block chunk" to the nearest whole transaction and to accompany it with
its corresponding array of transaction byte offsets.


# Development & Contributing
All commits should ideally pass through these checks first:

- pylint
- mypy type checker

Unit tests:

- pytest standard unittests
- pytest functional tests (runs against a regtest Bitcoin node with a pre-loaded test blockchain)

## Windows
There are a number of scripts provided to manage these testing procedures locally. Run them in numbered order.
Their function should be fairly self-explanatory.

-  `./scripts/0_win_build_base_image.bat`  <- only need to run this once in a while if 3rd party dependencies change
-  `./scripts/1_win_run_static_checks.bat`
-  `./scripts/2_win_run_tests.bat`

    These scripts work together and should be used in this order.
    They are divided up to allow running the node and importing blocks for other more manual testing scenarios.
    Or sometimes you will want to leave the node up and running so you can re-run the functional tests while
    iterating on a feature or bug fix.

-   `./scripts/3_win_node_up.bat`
-   `./scripts/4_win_import_blocks.bat`
-   `./scripts/5_win_run_tests_functional.bat`
-   `./scripts/6_win_node_down.bat`

These checks directly mirror the ones that run in the Azure pipeline.

### Not provided
If you want to handle re-enqueuing dropped messages due to disconnections, you would need to implement this 
yourself with a custom wrapper around the `BitcoinClientManager` perhaps with an outbound message queue with 
acking for messages that recieve a response and retry logic for various failure states (but not if rejected
by network rules). Either you want to queue it again on the same peer or you fail over to any random available 
peer. An example of this might be provided at a later date.