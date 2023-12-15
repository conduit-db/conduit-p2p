# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

import io
import json
import os
import time
from pathlib import Path

import bitcoinx
import pytest
from bitcoinx import hash_to_hex_str

from conduit_p2p.preprocessor import unpack_varint, tx_preprocessor
from .data.block413567_offsets import TX_OFFSETS

MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
os.environ["GENESIS_ACTIVATION_HEIGHT"] = "0"


with open(MODULE_DIR / "data/block413567.raw", "rb") as f:
    TEST_RAW_BLOCK_413567 = f.read()


def print_results(count_txs: int, t1: float, block_view: bytes) -> None:
    rate = count_txs / t1
    av_tx_size = round(len(block_view) / count_txs)
    bytes_per_sec = rate * av_tx_size
    MB_per_sec = round(bytes_per_sec / (1024 * 1024))

    print(
        f"block parsing took {round(t1, 5)} seconds for {count_txs} txs and"
        f" {len(block_view)} "
        f"bytes - therefore {round(rate)} txs per second for an average tx size "
        f"of {av_tx_size} bytes - therefore {MB_per_sec} MB/sec"
    )


def test_preprocessor_whole_block_as_a_single_chunk() -> None:
    full_block = bytearray(TEST_RAW_BLOCK_413567)
    tx_count, offset = unpack_varint(full_block[80:89], 0)
    assert tx_count == 1557
    block_hash_hex = hash_to_hex_str(bitcoinx.double_sha256(full_block[0:80]))
    assert block_hash_hex == "0000000000000000025aff8be8a55df8f89c77296db6198f272d6577325d4069"

    # Whole block as a single chunk
    tx_offsets_all: list[int] = []
    remainder = b""
    last_tx_offset_in_chunk = 0
    for idx, chunk in enumerate([full_block]):
        if idx == 0:
            tx_count, var_int_size = unpack_varint(full_block[80:89], 0)
            adjustment = 0
            offset = 80 + var_int_size
        else:
            adjustment = last_tx_offset_in_chunk
            offset = 0
        modified_chunk = remainder + chunk
        tx_offsets_for_chunk, last_tx_offset_in_chunk = tx_preprocessor(modified_chunk, offset, adjustment)
        tx_offsets_all.extend(tx_offsets_for_chunk)
        remainder = modified_chunk[last_tx_offset_in_chunk - adjustment :]

    assert tx_offsets_all == TX_OFFSETS
    assert last_tx_offset_in_chunk == len(full_block)
    print()


def test_preprocessor_with_block_divided_into_four_chunks() -> None:
    full_block = bytearray(TEST_RAW_BLOCK_413567)
    tx_count, offset = unpack_varint(full_block[80:89], 0)
    assert tx_count == 1557
    # Same block processed in 4 chunks
    chunks = [
        full_block[0:250_000],
        full_block[250_000:500_000],
        full_block[500_000:750_000],
        full_block[750_000:],
    ]

    t0 = time.perf_counter()

    tx_offsets_all: list[int] = []
    remainder = b""
    last_tx_offset_in_chunk = 0
    for idx, chunk in enumerate(chunks):
        if idx == 0:
            tx_count, var_int_size = unpack_varint(full_block[80:89], 0)
            adjustment = 0
            offset = 80 + var_int_size
        else:
            offset = 0
            adjustment = last_tx_offset_in_chunk
        modified_chunk = remainder + chunk
        tx_offsets_for_chunk, last_tx_offset_in_chunk = tx_preprocessor(modified_chunk, offset, adjustment)
        tx_offsets_all.extend(tx_offsets_for_chunk)
        remainder = modified_chunk[last_tx_offset_in_chunk - adjustment :]

        if idx == 0:
            assert tx_offsets_for_chunk[0] == 83
            assert tx_offsets_for_chunk[-1] == 248948
        if idx == 1:
            assert tx_offsets_for_chunk[0] == 249138
            assert tx_offsets_for_chunk[-1] == 423160
        if idx == 2:
            assert tx_offsets_for_chunk[0] == 482309
            assert tx_offsets_for_chunk[-1] == 749719
        if idx == 3:
            assert tx_offsets_for_chunk[0] == 749909
            assert tx_offsets_for_chunk[-1] == 999367
            assert last_tx_offset_in_chunk == 999887
            assert last_tx_offset_in_chunk == len(TEST_RAW_BLOCK_413567)

    t1 = time.perf_counter() - t0
    print()
    print_results(len(tx_offsets_all), t1, full_block)
    assert len(tx_offsets_all) == 1557
    assert tx_offsets_all == TX_OFFSETS


# This will only work if you have downloaded the >250MB block at height 593161 and downloaded
# it to data/block593161.hex. It's too large to include in CI/CD but I have included it here
# because it uncovered a bug in the preprocessor when I struck it on mainnet.
def test_preprocessor_on_256mb_block_593161() -> None:
    block593161_filepath = MODULE_DIR / "data" / "block593161.hex"
    if not block593161_filepath.exists():
        pytest.skip(
            "This test requires that you download the 256MB block at height 593161 " "to data/block593161.hex"
        )

    with open(block593161_filepath, "r") as file:
        rpc_result_json = file.read()

    rpc_result = json.loads(rpc_result_json)
    big_block = bytes.fromhex(rpc_result["result"])
    assert len(big_block) == 255996865
    raw_header = big_block[0:80]
    tx_count, offset = unpack_varint(big_block[80:89], 0)

    # BITCOINX
    stream = io.BytesIO(big_block[80 + offset :])
    adjustment = 80 + offset
    bitcoinx_tx_offsets = [adjustment]
    offset = adjustment
    tx_hashes_set = set()
    for i in range(tx_count):
        tx = bitcoinx.Tx.read(stream.read)
        offset += len(tx.to_bytes())
        bitcoinx_tx_offsets.append(offset)
        tx_hashes_set.add(tx.hex_hash())

    assert len(bitcoinx_tx_offsets) == tx_count + 1
    assert len(tx_hashes_set) == tx_count

    # CONDUIT PREPROCESSOR
    BUFFER_SIZE = 250_000_000  # block size is 255996865 so expect two chunks
    chunks = [
        big_block[0:BUFFER_SIZE],
        big_block[BUFFER_SIZE:],
    ]

    t0 = time.perf_counter()

    tx_offsets_all: list[int] = []
    remainder = b""
    last_tx_offset_in_chunk = 0
    for idx, chunk in enumerate(chunks):
        if idx == 0:
            tx_count, var_int_size = unpack_varint(big_block[80:89], 0)
            adjustment = 0
            offset = 80 + var_int_size
        else:
            adjustment = last_tx_offset_in_chunk
            offset = 0
        modified_chunk = remainder + chunk
        tx_offsets_for_chunk, last_tx_offset_in_chunk = tx_preprocessor(modified_chunk, offset, adjustment)
        tx_offsets_all.extend(tx_offsets_for_chunk)
        # adjustment here is effectively acting as the prev_last_tx_offset_in_chunk
        remainder = modified_chunk[last_tx_offset_in_chunk - adjustment :]
    t1 = time.perf_counter() - t0
    print()
    print_results(len(tx_offsets_all), t1, big_block)
    assert tx_offsets_all == bitcoinx_tx_offsets[:-1]
