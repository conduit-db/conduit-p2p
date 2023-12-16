# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.
import asyncio
import logging
import typing

from .client import BitcoinClient, DEFAULT_LARGE_MESSAGE_LIMIT
from .utils import cast_to_valid_ipv4

if typing.TYPE_CHECKING:
    from .handlers import HandlersDefault


class PeerManagerFailedError(Exception):
    pass


class BitcoinClientManager:
    """This can also manage multiple connections to the same node on the same port to overcome
    latency effects on data transfer rates.
    See: https://en.wikipedia.org/wiki/Bandwidth-delay_product"""

    def __init__(self, message_handler: 'HandlersDefault', peers_list: list[str],
            large_message_limit: int = DEFAULT_LARGE_MESSAGE_LIMIT) -> None:
        self.closing: bool = False
        self._logger = logging.getLogger("bitcoin-p2p-client-pool")
        self.message_handler = message_handler
        self.message_handler.client_manager = self
        self.large_message_limit = large_message_limit
        self.clients: list[BitcoinClient] = []
        for peer_id, host_string in enumerate(peers_list, start=1):
            host, port = host_string.split(":")
            host = cast_to_valid_ipv4(host)  # important for dns resolution of docker container IP addresses
            client = BitcoinClient(id=peer_id, remote_host=host, remote_port=int(port), message_handler=message_handler)
            self.clients.append(client)

        self._connection_pool: list[BitcoinClient] = []
        self._disconnected_pool: list[BitcoinClient] = []
        self._currently_selected_peer_index: int = 0

    async def __aenter__(self) -> "BitcoinClientManager":
        await self.connect_all_peers()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        await self.close()

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

    async def connect_all_peers(self) -> None:
        """Should have tolerance for some failed connections to offline peers"""
        for client in self.clients:
            try:
                await client.wait_for_connection()
                self._connection_pool.append(client)
            except ConnectionResetError:
                self._logger.error(
                    f"Failed to connect to peer. host: {client.remote_host}, " f"port: {client.remote_port}"
                )
                self._disconnected_pool.append(client)
        if len(self._connection_pool) == 0:
            raise PeerManagerFailedError("All connections failed")

    async def close(self) -> None:
        self.closing = True
        # Force close all outstanding connections
        outstanding_connections = list(self._connection_pool)
        for peer in outstanding_connections:
            if peer.connected:
                await peer.close()

    async def listen(self) -> None:
        """Should periodically check for disconnected peers and try to reconnect them on a sensible
        time schedule (frequently at first) and then less frequently."""
        while not self.closing:
            await asyncio.sleep(2)
