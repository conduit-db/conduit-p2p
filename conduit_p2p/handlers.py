# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.
import abc
import io
import logging
import typing
from math import ceil

from bitcoinx import hash_to_hex_str, double_sha256

from .deserializer import Deserializer
from .networks import NetworkConfig
from .serializer import Serializer
from .types import BlockChunkData, BlockDataMsg, BlockType, InvType

if typing.TYPE_CHECKING:
    from .client_manager import BitcoinClientManager
    from .client import BitcoinClient


class HandlersDefault(abc.ABC):
    """For many use-cases, it's not necessary to flesh out all of these handlers but
    the bare minumum handlers have default implementations"""
    def __init__(
        self,
        network_type: str,
    ) -> None:
        self.net_config = NetworkConfig(network_type=network_type)
        self.serializer = Serializer(self.net_config)
        self.deserializer = Deserializer(self.net_config)
        self.logger = logging.getLogger("conduit-p2p-handlers")
        self.client_manager: 'BitcoinClientManager | None' = None

        self.getdata_txs_all: bool = False
        self.getdata_blocks_all: bool = False

    async def on_version(self, message: bytes, peer: 'BitcoinClient') -> None:
        version = self.deserializer.version(io.BytesIO(message))
        self.logger.debug("Received version: %s (peer_id=%s)", version, peer.id)
        verack_message = self.serializer.verack()
        self.logger.debug("Sending verack")
        peer.send_message(verack_message)

    async def on_verack(self, message: bytes, peer: 'BitcoinClient') -> None:
        self.logger.debug("Received verack (peer_id=%s)", peer.id)  # No payload

    async def on_protoconf(self, message: bytes, peer: 'BitcoinClient') -> None:
        protoconf = self.deserializer.protoconf(io.BytesIO(message))
        self.logger.debug("Received protoconf %r from peer: %s", protoconf, peer.id)

    async def on_sendheaders(self, message: bytes, peer: 'BitcoinClient') -> None:
        self.logger.debug("Received sendheaders (peer_id=%s)", peer.id)  # No payload

    async def on_sendcmpct(self, message: bytes, peer: 'BitcoinClient') -> None:
        self.logger.debug("Received sendcmpct (peer_id=%s)", peer.id)
        sendcmpct = self.serializer.sendcmpct()
        peer.send_message(sendcmpct)

    async def on_ping(self, message: bytes, peer: 'BitcoinClient') -> None:
        self.logger.debug(f"Received ping (peer_id=%s)", peer.id)
        pong_message = self.serializer.pong(message)
        self.logger.debug(f"Sending pong (peer_id=%s)", peer.id)
        peer.send_message(pong_message)

    async def on_pong(self, message: bytes, peer: 'BitcoinClient') -> None:
        pong = self.deserializer.pong(io.BytesIO(message))
        self.logger.debug("Received pong, nonce=%s (peer_id=%s)", pong, peer.id)

    async def on_addr(self, message: bytes, peer: 'BitcoinClient') -> None:
        addr = self.deserializer.addr(io.BytesIO(message))
        self.logger.debug("Received addr: %s (peer_id=%s)", addr, peer.id)

    async def on_feefilter(self, message: bytes, peer: 'BitcoinClient') -> None:
        feefilter = self.deserializer.feefilter(io.BytesIO(message))
        self.logger.debug("Received feefilter: %s (peer_id=%s)", feefilter, peer.id)

    async def on_authch(self, message: bytes, peer: 'BitcoinClient') -> None:
        self.logger.debug("Received authch (peer_id=%s)", peer.id)

    async def on_inv(self, message: bytes, peer: 'BitcoinClient') -> None:
        inv_vect = self.deserializer.inv(io.BytesIO(message))
        self.logger.debug("Received inv: %s (peer_id=%s)", inv_vect, peer.id)

        if not self.getdata_txs_all and not self.getdata_blocks_all:
            return

        tx_inv_vect = []
        block_inv_vect = []
        for inv in inv_vect:
            # TX
            if inv["inv_type"] == InvType.TX:
                tx_inv_vect.append(inv)

            # BLOCK
            elif inv["inv_type"] == InvType.BLOCK:
                block_inv_vect.append(inv)

        if block_inv_vect and self.getdata_blocks_all:
            max_getdata_size = 50_000
            num_getdatas = ceil(len(block_inv_vect) / max_getdata_size)
            for i in range(num_getdatas):
                getdata_msg = self.serializer.getdata(block_inv_vect[i : (i + 1) * max_getdata_size])
                peer.send_message(getdata_msg)

        if tx_inv_vect and self.getdata_txs_all:
            max_getdata_size = 50_000
            num_getdatas = ceil(len(tx_inv_vect) / max_getdata_size)
            for i in range(num_getdatas):
                getdata_msg = self.serializer.getdata(tx_inv_vect[i : (i + 1) * max_getdata_size])
                peer.send_message(getdata_msg)

    async def on_getdata(self, message: bytes, peer: 'BitcoinClient') -> None:
        getdata = self.deserializer.getdata(io.BytesIO(message))
        self.logger.debug("Received getdata: %s (peer_id=%s)", getdata, peer.id)

    async def on_headers(self, message: bytes, peer: 'BitcoinClient') -> None:
        headers = self.deserializer.headers(io.BytesIO(message))
        self.logger.debug("Received headers: %s (peer_id=%s)", headers, peer.id)

    async def on_tx(self, rawtx: bytes, peer: 'BitcoinClient') -> None:
        tx = self.deserializer.tx(io.BytesIO(rawtx))
        self.logger.debug("Received rawtx: %s (peer_id=%s)", tx.hex_hash(), peer.id)

    async def on_reject(self, message: bytes, peer: 'BitcoinClient') -> None:
        reject_msg = self.deserializer.reject(io.BytesIO(message))
        self.logger.debug("Received reject: %s (peer_id=%s)", reject_msg, peer.id)

    async def on_block_chunk(self, block_chunk_data: BlockChunkData, peer: 'BitcoinClient') -> None:
        """These block chunks are sized to the nearest whole transaction. This allows parallel processing.
        The transaction offsets are also provided for quick random access"""
        self.logger.debug("Received big block chunk number %s with block_hash: %s (peer_id=%s)",
            block_chunk_data.chunk_num, hash_to_hex_str(block_chunk_data.block_hash), peer.id)

    async def on_block(self, block_data_msg: BlockDataMsg, peer: 'BitcoinClient') -> None:
        """Small blocks are provided as one blob, whereas big blocks (exceeding LARGE_MESSAGE_LIMIT)
        are provided as chunks in the `on_block_chunk` callback."""
        block_hash = double_sha256(block_data_msg.block_hash)
        if block_data_msg.block_type == BlockType.SMALL_BLOCK:
            self.logger.debug("Received small block with block_hash: %s (peer_id=%s)",
                hash_to_hex_str(block_hash), peer.id)
        else:
            self.logger.debug("Received all big block chunks for block_hash: %s (peer_id=%s)",
                hash_to_hex_str(block_hash), peer.id)
