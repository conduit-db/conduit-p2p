import logging

from .client import BitcoinClient


class PeerManagerFailedError(Exception):
    pass


class BitcoinClientManager:
    """This can also manage multiple connections to the same node on the same port to overcome
    latency effects on data transfer rates.
    See: https://en.wikipedia.org/wiki/Bandwidth-delay_product"""

    def __init__(self, clients: list[BitcoinClient]) -> None:
        self._logger = logging.getLogger("bitcoin-p2p-client-pool")
        self.clients = clients
        self._connection_pool: list[BitcoinClient] = []
        self._disconnected_pool: list[BitcoinClient] = []
        self._currently_selected_peer_index: int = 0

    def __len__(self) -> int:
        return len(self._connection_pool)

    def add_client(self, client: BitcoinClient) -> None:
        self.clients.append(client)

    def select_next_peer(self) -> None:
        if self._currently_selected_peer_index == len(self._connection_pool) - 1:
            self._currently_selected_peer_index = 0
        else:
            self._currently_selected_peer_index += 1

    def get_connected_peers(self) -> list[BitcoinClient]:
        return self._connection_pool

    def get_next_peer(self) -> BitcoinClient:
        self.select_next_peer()
        return self.get_current_peer()

    def get_current_peer(self) -> BitcoinClient:
        return self._connection_pool[self._currently_selected_peer_index]

    async def try_connect_to_all_peers(self) -> None:
        """Should have tolerance for some failed connections to offline peers"""
        for client in self.clients:
            try:
                await client.wait_for_connection()
                self._connection_pool.append(client)
            except ConnectionResetError:
                self._logger.error(
                    f"Failed to connect to peer. host: {client.peer.host}, " f"port: {client.peer.port}"
                )
                self._disconnected_pool.append(client)
        if len(self._connection_pool) == 0:
            raise PeerManagerFailedError("All connections failed")

    async def try_handshake_for_all_peers(self, local_host: str, local_port: int) -> None:
        for client in self._connection_pool:
            await client.handshake(local_host, local_port)

    async def close(self) -> None:
        # Force close all outstanding connections
        outstanding_connections = list(self._connection_pool)
        for conn in outstanding_connections:
            if conn.connected:
                await conn.close_connection()
