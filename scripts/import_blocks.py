# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

"""
Import the blocks exported to a local directory into a running node.

> py import_blocks.py <local directory>

The directory should contain a `headers.txt` file and an additional file for each block named
as the hash for the given block.
"""

import json
import os
import requests
import sys

RPC_URI = "http://rpcuser:rpcpassword@127.0.0.1:18332"


def submit_block(block_bytes: bytes) -> None:
    block_bytes_hex = block_bytes.hex()
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "submitblock",
            "params": [block_bytes_hex],
            "id": 0,
        }
    )
    result = requests.post(f"{RPC_URI}", data=payload, timeout=10.0)
    result.raise_for_status()


def validate_inputs(blockchain_dir: str):
    output_dir_path = os.path.realpath(blockchain_dir)
    if not os.path.exists(output_dir_path) or not os.path.isdir(output_dir_path):
        print(f"Directory does not exist: {blockchain_dir}")
        sys.exit(1)

    headers_file_path = os.path.join(output_dir_path, "headers.txt")
    if not os.path.exists(headers_file_path):
        print(f"Directory does not look like a blockchain export: {blockchain_dir}")
        sys.exit(1)
    return output_dir_path, headers_file_path


def get_header_hash_hexs(headers_file_path: str, output_dir_path: str):
    header_hash_hexs: list[str] = []
    with open(headers_file_path, "r") as hf:
        i = 0
        while 1:
            header_hash_hex = hf.readline().strip()
            if not header_hash_hex:
                break
            block_file_path = os.path.join(output_dir_path, header_hash_hex)
            if not os.path.exists(block_file_path):
                print(f"Missing block {i} {header_hash_hex[:6]}")
                sys.exit(1)
            header_hash_hexs.append(header_hash_hex)
            i += 1
    return header_hash_hexs


def submit_blocks(header_hash_hexs: list[str], output_dir_path: str):
    for i, header_hash_hex in enumerate(header_hash_hexs):
        print(f"Uploading block {i} {header_hash_hex[:6]}")
        block_file_path = os.path.join(output_dir_path, header_hash_hex)
        with open(block_file_path, "rb") as bf:
            block_bytes = bf.read()
            submit_block(block_bytes)


def import_blocks(blockchain_dir: str):
    output_dir_path, headers_file_path = validate_inputs(blockchain_dir)
    header_hash_hexs = get_header_hash_hexs(headers_file_path, output_dir_path)
    submit_blocks(header_hash_hexs, output_dir_path)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"{sys.argv[0]} <directory path>")
        sys.exit(1)

    import_blocks(sys.argv[1])
    sys.exit(0)


if __name__ == "__main__":
    main()
