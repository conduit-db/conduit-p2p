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

The constructor of the example `MyApplicationHandlers` below is where you could add significant application state
to push messages into queues, write to files or databases, trigger events, route messages to worker
processes for parsing, update a redis cache etc. 

There is a single instance of the `MyApplicationHandlers` which is shared by all `BitcoinClient` connections. Within
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

### Multiple Peers (Recommended)
It's possible to create multiple connections to the same node for concurrency or connect to multiple 
geographically dispersed peers. 

The API is almost identical as for a single peer connection.

If you call `client_manager.get_next_peer()` in a loop before each request it will round-robin load balance evenly
across all peers. How you select peers is entirely up to you.
```python
import asyncio
import io
import logging
from conduit_p2p import BitcoinClient, BitcoinClientManager, REGTEST, HandlersDefault


logging.basicConfig(format="%(asctime)-25s %(levelname)-10s %(name)-28s %(message)s")


class SPVApplicationHandlers(HandlersDefault):
    """Override the other callbacks as you need to."""

    def __init__(self, network_type: str):
        super().__init__(network_type=network_type)
        self.logger = logging.getLogger("conduit-p2p-handlers")
        self.logger.setLevel(logging.DEBUG)  # To silence the logs from the default handlers, set a higher level

    async def on_headers(self, message: bytes, peer: BitcoinClient) -> None:
        headers = self.deserializer.headers(io.BytesIO(message))
        self.logger.debug(f"Received headers (peer_id={peer.id})")
        for header in headers:
            self.logger.debug(f"header: {header}")

        await self.client_manager.close()  # <-- This will exit the listening loop and close all connections gracefully
        # await peer.close()  # <-- Alternatively this would do the same for a single peer

    async def on_inv(self, message: bytes, peer: BitcoinClient) -> None:
        inv_vect = self.deserializer.inv(io.BytesIO(message))
        self.logger.debug("Received inv: %s (peer_id=%s)", inv_vect, peer.id)

    async def on_reject(self, message: bytes, peer: BitcoinClient) -> None:
        reject_msg = self.deserializer.reject(io.BytesIO(message))
        self.logger.debug("Received reject: %s (peer_id=%s)", reject_msg, peer.id)


async def main():
    message_handler = SPVApplicationHandlers(REGTEST)
    peers_list = ["127.0.0.1:18444", "127.0.0.1:18444", "127.0.0.1:18444"]

    async with BitcoinClientManager(message_handler, peers_list) as client_manager:
        rawtx: bytes = b"raw transaction goes here"
        for _ in range(len(client_manager.clients)):
            client = client_manager.get_next_peer()
            client.broadcast_transaction(rawtx)

        message = client.serializer.getheaders(
            hash_count=1,
            block_locator_hashes=[bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000")],
            hash_stop=bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000")
        )
        client.send_message(message)
        # blocks until `await client_manager.close()` is called above in the `on_headers` handler
        # You could also enter an app main loop or wait for an event from the handler
        await client_manager.listen()

asyncio.run(main())

```

### Single Peer
If you only want to connect to as single peer, you can do it like this.
```python
    async def main():
        message_handler = SPVApplicationHandlers(REGTEST)
        rawtx: bytes = b"raw transaction goes here"

        async with BitcoinClient(1, remote_host="127.0.0.1", remote_port=18444, message_handler=message_handler) as client:
            client.broadcast_transaction(rawtx)
    
            message = client.serializer.getheaders(
                hash_count=1,
                block_locator_hashes=[bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000")],
                hash_stop=bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000")
            )
            client.send_message(message)
            # blocks until `await peer.close()` is called above in the `on_headers` handler
            # You could also enter an app main loop or wait for an event from your handler
            await client.listen()

    asyncio.run(main())

```

The most important handlers for a lightweight SPV client might include only:

- `on_headers`
- `on_reject`
- `on_inv`

An indexer might require these additional handlers:

- `on_tx`
- `on_block`        # discussed more below
- `on_block_chunk`  # discussed more below

You don't need to use `BitcoinClient` or `BitcoinClientManager` with the context manager API. 
You can also use it like this:

```python
    async def main():
        message_handler = SPVApplicationHandlers(REGTEST)
        client = BitcoinClient(1, remote_host="127.0.0.1", remote_port=18444, message_handler=message_handler)
        await client.connect()
        message = client.serializer.getheaders(
            hash_count=1,
            block_locator_hashes=[bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000")],
            hash_stop=bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000")
        )
        client.send_message(message)
        await client.listen()
        # Do something else after having received the headers
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