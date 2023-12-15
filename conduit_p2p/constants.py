# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

# Object types
from enum import IntEnum

MAX_BLOCK_PER_BATCH_COUNT_CONDUIT_INDEX = 1000
MAX_BLOCK_PER_BATCH_COUNT_CONDUIT_RAW = 500  # p2p network doesn't allow any more than this
MAX_BLOCKS_SYNCRONIZED_AHEAD = 1000  # Max number of blocks ConduitRaw can get ahead of ConduitIndex

ERROR = 0
MSG_TX = 1
MSG_BLOCK = 2
MSG_FILTERED_BLOCK = 3
MSG_CMPCT_BLOCK = 4

CCODES = {
    "0x01": "REJECT_MALFORMED",
    "0x10": "REJECT_INVALID",
    "0x11": "REJECT_OBSOLETE",
    "0x12": "REJECT_DUPLICATE",
    "0x40": "REJECT_NONSTANDARD",
    "0x41": "REJECT_DUST",
    "0x42": "REJECT_INSUFFICIENTFEE",
    "0x43": "REJECT_CHECKPOINT",
}

LOGGING_FORMAT = "%(asctime)s %(levelname)s %(message)s"

HashXLength = 11
MAX_UINT32 = 2**32 - 1

BLOCK_HEADER_LENGTH = 80
ZERO_HASH = b"00" * 32
GENESIS_BLOCK = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
NULL_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

MAINNET = "mainnet"
TESTNET = "testnet"
SCALINGTESTNET = "scaling-testnet"
REGTEST = "regtest"
LOGGING_LEVEL_VARNAME = "logging_level"


class MsgType(IntEnum):
    ERROR = 0
    MSG_TX = 1
    MSG_BLOCK = 2
    MSG_FILTERED_BLOCK = 3
    MSG_CMPCT_BLOCK = 4
