import asyncio
import io
import logging

from conduit_p2p import BitcoinClient, REGTEST, HandlersDefault

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

        await peer.close()  # <-- This will exit the listening loop and close the connection gracefully

    async def on_inv(self, message: bytes, peer: BitcoinClient) -> None:
        inv_vect = self.deserializer.inv(io.BytesIO(message))
        self.logger.debug("Received inv: %s (peer_id=%s)", inv_vect, peer.id)

    async def on_reject(self, message: bytes, peer: BitcoinClient) -> None:
        reject_msg = self.deserializer.reject(io.BytesIO(message))
        self.logger.debug("Received reject: %s (peer_id=%s)", reject_msg, peer.id)


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
