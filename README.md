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

### Simplified API (for SPV wallets / apps)
The simplified API (i.e. `mode=BitcoinClientMode.SIMPLE`) uses 
internal queues which redirects messages from the handlers.

It also unlocks the usage of helper functions:

- `BitcoinClient.broadcast_transaction`
- `BitcoinClient.get_headers`

For basic use cases this is acceptable and allows us
to approximate a request/response pattern. 

For more advanced applications like blockchain indexers you will likely need to use the "Advanced" API 
where you over-ride some or all of the `HandlersDefault`handlers. Although even then, it may not
necessarily be required.

```python
import asyncio
from io import BytesIO
import logging

from bitcoinx import hash_to_hex_str

from conduit_p2p import BitcoinClientManager, REGTEST, HandlersDefault
from conduit_p2p.constants import ZERO_HASH
from conduit_p2p.types import BlockHeader, BitcoinClientMode, BroadcastResult

logging.basicConfig(format="%(asctime)-25s %(levelname)-10s %(name)-28s %(message)s")

async def main():
    logger = logging.getLogger('main')
    logger.setLevel(logging.DEBUG)
    message_handler = HandlersDefault(REGTEST)
    peers_list = ["127.0.0.1:18444", "127.0.0.1:18444", "127.0.0.1:18444"]

    async with BitcoinClientManager(message_handler, peers_list,
            mode=BitcoinClientMode.SIMPLE) as client_manager:

        # ccode_translation=REJECT_MALFORMED
        rawtx: bytes = b"raw transaction goes here"
        result: BroadcastResult = await client_manager.broadcast_transaction_and_listen(rawtx,
            broadcast_peer_count=1)
        if result.rejected is not None:
            logger.error(f"Transaction rejected. Reason: {result.rejected}")

        client = await client_manager.get_next_available_peer()
        
        # Get up to the first 2000 headers
        message = await client.get_headers(
            hash_count=1,
            block_locator_hashes=[ZERO_HASH],
            hash_stop=ZERO_HASH
        )
        if message:
            headers: list[BlockHeader] = client.deserializer.headers(BytesIO(message))
            for header in headers:
                logger.debug(f"Got header. Hash: {hash_to_hex_str(header.hash)}")

        # See the examples/ folder for a fuller demonstration of acquiring all headers

        logger.debug(f"Waiting for the new chain tip")
        while True:
            inv_vect = await client.inv_queue.get()
            logger.debug(f"Got inv_vect: {inv_vect}")  # <- reconcile and maybe send getheaders

asyncio.run(main())

```

### Advanced API
The advanced API (i.e. `mode=BitcoinClientMode.ADVANCED`) turns off
any "magic" helper functionality and expects you to over-ride the
relevant default handlers for your use case.

These functions will raise a ValueError if you try to use them:

- BitcoinClient.broadcast_transaction
- BitcoinClient.get_headers

Instead, every message type follows the same low-level pattern of
serializing & then sending.

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
    """Override the other callbacks as you need to."""

    def __init__(self, network_type: str):
        super().__init__(network_type)
        self.logger.setLevel(logging.DEBUG)  # To silence the logs from the default handlers, set a higher level

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
    message_handler = SPVApplicationHandlers(REGTEST)
    peers_list = ["127.0.0.1:18444", "127.0.0.1:18444", "127.0.0.1:18444"]
    async with BitcoinClientManager(message_handler, peers_list, mode=BitcoinClientMode.ADVANCED) as client_manager:
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