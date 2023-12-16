# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.
import time

from electrumsv_node import electrumsv_node
import os
from pathlib import Path
import subprocess


MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

extra_config_options = [
    "-debug=1",
    "-rejectmempoolrequest=0",
    "-rpcallowip=0.0.0.0/0",
    "-rpcbind=0.0.0.0",
    # `docker network ls` then `docker network inspect <network name>` will show the netmask.
    "-whitelist=172.0.0.0/8",
    "-rpcthreads=100",
]


def load_initial_blockchain_thread():
    while electrumsv_node.call_any("getinfo").json()["result"]["blocks"] < 115:
        time.sleep(0.2)

    # Mine one additional block to take the node out of initial block download mode
    electrumsv_node.call_any("generate", 1, rpchost="localhost")


split_command = electrumsv_node.shell_command(print_to_console=True, extra_params=extra_config_options)
process = subprocess.Popen(" ".join(split_command), shell=True, env=os.environ.copy())
process.wait()
