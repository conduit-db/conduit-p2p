# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.
import asyncio
import logging
import typing
from typing import Iterable
from random import random

from bitcoinx import double_sha256

from .client import BitcoinClient, DEFAULT_LARGE_MESSAGE_LIMIT
from .types import BitcoinClientMode, Reject, BroadcastResult
from .utils import cast_to_valid_ipv4, create_task

if typing.TYPE_CHECKING:
    from .handlers import HandlersDefault


class PeerManagerFailedError(Exception):
    pass


class BitcoinClientManager:
    """This can also manage multiple connections to the same node on the same port to overcome
    latency effects on data transfer rates.
    See: https://en.wikipedia.org/wiki/Bandwidth-delay_product"""

    def __init__(self, message_handler: 'HandlersDefault', peers_list: list[str],
            large_message_limit: int = DEFAULT_LARGE_MESSAGE_LIMIT,
            mode: BitcoinClientMode = BitcoinClientMode.SIMPLE,
            relay_transactions: bool = True
    ) -> None:
        self.closing: bool = False
        self._logger = logging.getLogger("bitcoin-p2p-client-pool")
        self._logger.setLevel(logging.DEBUG)
        self.message_handler = message_handler
        self.message_handler.client_manager = self
        self.net_config = message_handler.net_config
        self.serializer = message_handler.serializer
        self.deserializer = message_handler.deserializer
        self.large_message_limit = large_message_limit
        self.clients: list[BitcoinClient] = []
        self.mode = mode
        for peer_id, host_string in enumerate(peers_list, start=1):
            host, port = host_string.split(":")
            host = cast_to_valid_ipv4(host)  # important for dns resolution of docker container IP addresses
            client = BitcoinClient(id=peer_id, remote_host=host, remote_port=int(port),
                message_handler=message_handler, mode=mode, relay_transactions=relay_transactions)
            self.clients.append(client)

        self._connection_pool: list[BitcoinClient] = []
        self._disconnected_pool: list[BitcoinClient] = []
        self._currently_selected_peer_index: int = 0

        # On tx broadcast, record acceptance by other peers
        self.tx_inv_queue_map: dict[bytes, list[int]] = {} # tx_hash -> list[BitcoinClient.id]

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
        """This will iterate through all clients regardless of whether they are connected or not"""
        if self._currently_selected_peer_index == len(self.clients) - 1:
            self._currently_selected_peer_index = 0
        else:
            self._currently_selected_peer_index += 1

    def get_connected_peers(self) -> list[BitcoinClient]:
        return self._connection_pool

    def get_next_peer(self) -> BitcoinClient:
        self.select_next_peer()
        return self.get_current_peer()

    async def get_next_available_peer(self) -> BitcoinClient:
        while len(self._connection_pool) < 1:
            self._logger.info(f"Waiting for peers to connect")
            await asyncio.sleep(1)
        client = self.get_next_peer()
        while client not in self.get_connected_peers():
            self._logger.debug(f"Peer {client.id} is unavailable. Selecting next peer")
            client = self.get_next_peer()
            if not self.get_connected_peers():
                self._logger.debug(f"No available peers. Waiting")
                await asyncio.sleep(1)  # avoid spinning
        return client

    def get_current_peer(self) -> BitcoinClient:
        """This peer might be disconnected. Requires filtering"""
        return self.clients[self._currently_selected_peer_index]

    async def connect_all_peers(self) -> None:
        """Should have tolerance for some failed connections to offline peers"""
        async def connect_task() -> None:
            try:
                await client.wait_for_connection()
                self._connection_pool.append(client)
            except ConnectionResetError:
                self._logger.error(
                    f"Failed to connect to peer. host: {client.remote_host}, " f"port: {client.remote_port}"
                )
                self._disconnected_pool.append(client)

        for client in self.clients:
            create_task(connect_task())
            await asyncio.sleep(random()*2)  # avoid thundering herd on the same node
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

    async def _concurrent_broadcast(self, rawtx: bytes, wait_time: float,
            broadcast_peer_count: int, check_malformed: bool, available_peers_count: int) -> Iterable[Reject | None]:
        tasks = []
        # Concurrently broadcast to (up to) `broadcast_peer_count` peers
        # If fewer than this many peers are available, broadcast to as many
        # as are available
        for _ in range(min(broadcast_peer_count, available_peers_count)):
            client = await self.get_next_available_peer()
            task = create_task(client.broadcast_transaction(rawtx, wait_time=wait_time,
                check_malformed=check_malformed))
            tasks.append(task)

        return await asyncio.gather(*tasks, return_exceptions=False)

    async def broadcast_transaction_and_listen(self, rawtx: bytes, wait_time: float=5.0,
            broadcast_peer_count: int = 1, check_malformed: bool = True) -> BroadcastResult:
        if self.mode != BitcoinClientMode.SIMPLE:
            raise ValueError("This helper method is only available in BitcoinClientMode.SIMPLE mode")

        available_peers_count = len(self.get_connected_peers())
        if available_peers_count == 0:
            raise ValueError(f"No available peers for broadcast")

        if len(rawtx) == 0:
            rejected: Reject | None = Reject(message='tx', ccode_translation='REJECT_MALFORMED',
                reason='error parsing message', item_hash='')
            return BroadcastResult(rejected=rejected, relaying_peer_ids=[])

        tx_hash = double_sha256(rawtx)
        try:
            if self.tx_inv_queue_map.get(tx_hash):
                raise ValueError("This transaction is already in the process of being broadcast")
            self.tx_inv_queue_map[tx_hash] = []

            results = await self._concurrent_broadcast(rawtx, wait_time, broadcast_peer_count,
                check_malformed, available_peers_count)

            for reject in results:
                if reject is not None:
                    return BroadcastResult(rejected=reject, relaying_peer_ids=[])

            relaying_peer_ids = self.tx_inv_queue_map[tx_hash]
            return BroadcastResult(rejected=None, relaying_peer_ids=relaying_peer_ids)
        finally:
            del self.tx_inv_queue_map[tx_hash]
