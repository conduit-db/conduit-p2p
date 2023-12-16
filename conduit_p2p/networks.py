# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

import logging
import random
from collections import namedtuple
from typing import cast

from bitcoinx import (
    CheckPoint,
    Bitcoin,
    BitcoinTestnet,
    BitcoinScalingTestnet,
    BitcoinRegtest,
    Headers,
    MissingHeader,
    Network,
)
from bitcoinx.chain import Chain
from bitcoinx.networks import Header

from .constants import MAINNET, TESTNET, SCALINGTESTNET, REGTEST
from .utils import cast_to_valid_ipv4

logger = logging.getLogger("networks")

Peer = namedtuple("Peer", ["remote_host", "remote_port"])


class HeadersRegTestMod(Headers):  # type: ignore[misc]
    def connect(self, raw_header: bytes) -> tuple[Header, Chain]:
        """overwrite Headers method to skip checking of difficulty target"""
        header = BitcoinRegtest.deserialized_header(raw_header, -1)
        prev_header, chain = self.lookup(header.prev_hash)
        header.height = prev_header.height + 1
        # If the chain tip is the prior header then this header is new. Otherwise, we must check.
        if chain.tip.hash != prev_header.hash:
            try:
                return cast(tuple[Header, Chain], self.lookup(header.hash))
            except MissingHeader:
                pass
        header_index = self._storage.append(raw_header)
        chain = self._read_header(header_index)
        return header, chain


class AbstractNetwork:
    NET = ""
    PUBKEY_HASH = 0x00
    PRIVATEKEY = 0x00
    SCRIPTHASH = 0x00
    XPUBKEY = 0x00000000
    XPRIVKEY = 0x00000000
    MAGIC = 0x00000000
    PORT = 0000
    DNS_SEEDS = [""]
    BITCOINX_COIN: Network | None = None
    CHECKPOINT: CheckPoint | None = None
    GENESIS_BLOCK_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    GENESIS_ACTIVATION_HEIGHT = 0


class MainNet(AbstractNetwork):
    NET = MAINNET
    PUBKEY_HASH = 0x00
    PRIVATEKEY = 0x80
    SCRIPTHASH = 0x05
    XPUBKEY = 0x0488B21E
    XPRIVKEY = 0x0488ADE4
    MAGIC = 0xE3E1F3E8
    PORT = 8333
    DNS_SEEDS = ["seed.bitcoinsv.io"]
    BITCOINX_COIN = Bitcoin
    GENESIS_BLOCK_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    # i.e. Genesis block
    CHECKPOINT = CheckPoint(
        bytes.fromhex(
            "010000000000000000000000000000000000000000000000000000000000000000000000"
            "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49"
            "ffff001d1dac2b7c"
        ),
        height=0,
        prev_work=0,
    )
    GENESIS_ACTIVATION_HEIGHT = 620_538


class TestNet(AbstractNetwork):
    NET = TESTNET
    PUBKEY_HASH = 0x6F
    PRIVATEKEY = 0xEF
    SCRIPTHASH = 0xC4
    XPUBKEY = 0x043587CF
    XPRIVKEY = 0x04358394
    MAGIC = 0xF4E5F3F4
    PORT = 18333
    DNS_SEEDS = ["testnet-seed.bitcoinsv.io"]
    BITCOINX_COIN = BitcoinTestnet
    GENESIS_BLOCK_HASH = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"
    # i.e. Genesis block
    CHECKPOINT = CheckPoint(
        bytes.fromhex(
            "010000000000000000000000000000000000000000000000000000000000000000000000"
            "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4adae5494d"
            "ffff001d1aa4ae18"
        ),
        height=0,
        prev_work=0,
    )
    GENESIS_ACTIVATION_HEIGHT = 1_344_302


class ScalingTestNet(AbstractNetwork):
    NET = SCALINGTESTNET
    PUBKEY_HASH = 0x6F
    PRIVATEKEY = 0xEF
    SCRIPTHASH = 0xC4
    XPUBKEY = 0x043587CF
    XPRIVKEY = 0x04358394
    MAGIC = 0xFBCEC4F9
    PORT = 9333
    DNS_SEEDS = ["stn-seed.bitcoinsv.io"]
    BITCOINX_COIN = BitcoinScalingTestnet
    GENESIS_BLOCK_HASH = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"
    # i.e. Genesis block
    CHECKPOINT = CheckPoint(
        bytes.fromhex(
            "010000000000000000000000000000000000000000000000000000000000000000000000"
            "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4adae5494"
            "dffff001d1aa4ae18"
        ),
        height=0,
        prev_work=0,
    )
    VERIFICATION_BLOCK_MERKLE_ROOT = None
    GENESIS_ACTIVATION_HEIGHT = 100


class RegTestNet(AbstractNetwork):
    NET = REGTEST
    PUBKEY_HASH = 0x6F
    PRIVATEKEY = 0xEF
    SCRIPTHASH = 0xC4
    XPUBKEY = 0x043587CF
    XPRIVKEY = 0x04358394
    MAGIC = 0xDAB5BFFA
    PORT = 18444
    DNS_SEEDS = ["127.0.0.1"]
    BITCOINX_COIN = BitcoinRegtest
    GENESIS_BLOCK_HASH = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206"
    # i.e. Genesis block
    CHECKPOINT = CheckPoint(
        bytes.fromhex(
            "010000000000000000000000000000000000000000000000000000000000000000000000"
            "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4adae5494d"
            "ffff7f2002000000"
        ),
        height=0,
        prev_work=0,
    )
    GENESIS_ACTIVATION_HEIGHT = 10_000


class NetworkConfig:
    def __init__(
        self,
        network_type: str,
        node_host: str,
        node_port: int,
        node_rpc_host: str = "127.0.0.1",
        node_rpc_port: int = 18332,
    ) -> None:
        network: AbstractNetwork = NETWORKS[network_type]
        self.node_host = cast_to_valid_ipv4(node_host)
        self.node_port = node_port
        self.node_rpc_host = cast_to_valid_ipv4(node_rpc_host)
        self.node_rpc_port = node_rpc_port
        self.NET = network.NET
        self.PUBKEY_HASH = network.PUBKEY_HASH
        self.PRIVATEKEY = network.PRIVATEKEY
        self.SCRIPTHASH = network.SCRIPTHASH
        self.XPUBKEY = network.XPUBKEY
        self.XPRIVKEY = network.XPRIVKEY
        self.MAGIC = network.MAGIC
        self.PORT = network.PORT
        self.DNS_SEEDS = network.DNS_SEEDS
        self.BITCOINX_COIN: Network = network.BITCOINX_COIN
        self.GENESIS_BLOCK_HASH: str = network.GENESIS_BLOCK_HASH
        self.CHECKPOINT: CheckPoint = network.CHECKPOINT
        self.GENESIS_ACTIVATION_HEIGHT = network.GENESIS_ACTIVATION_HEIGHT

        self.peers: list[Peer] = []
        self._currently_selected_peer_index: int = 0
        self.set_peers(network)

    def get_peer(self) -> "Peer":
        return self.peers[random.randint(0, len(self.peers) - 1)]

    def select_next_peer(self) -> None:
        if self._currently_selected_peer_index == len(self.peers) - 1:
            self._currently_selected_peer_index = 0
        else:
            self._currently_selected_peer_index += 1

    def get_next_peer(self) -> "Peer":
        self.select_next_peer()
        return self.peers[self._currently_selected_peer_index]

    def get_default_peers(self, network: AbstractNetwork) -> None:
        if isinstance(network, RegTestNet):
            self.peers = [Peer("127.0.0.1", 18444)]
        if isinstance(network, TestNet):
            self.peers = [Peer("127.0.0.1", 18333)]
        if isinstance(network, ScalingTestNet):
            self.peers = [Peer("116.202.171.166", 9333)]
        elif isinstance(network, MainNet):
            self.peers = [Peer("127.0.0.1", 8333)]

    def set_peers(self, network: AbstractNetwork) -> None:
        if self.node_host:
            # in docker a container name needs dns resolution
            host = self.node_host
            port = int(self.node_port)
            self.peers = [Peer(host, port)]
        else:
            self.get_default_peers(network)


NETWORKS = {
    MAINNET: MainNet(),
    TESTNET: TestNet(),
    SCALINGTESTNET: ScalingTestNet(),
    REGTEST: RegTestNet(),
}
