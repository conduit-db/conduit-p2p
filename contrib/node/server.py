# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.
from electrumsv_node import electrumsv_node
import os
from pathlib import Path
import subprocess


MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

extra_config_options = [
    "-debug=1",
    "-rejectmempoolrequest=1",
    "-rpcallowip=0.0.0.0/0",
    "-rpcbind=0.0.0.0",
    # `docker network ls` then `docker network inspect <network name>` will show the netmask.
    # "-whitelist=172.0.0.0/8",
    "-rpcthreads=100",
]

split_command = electrumsv_node.shell_command(print_to_console=True, extra_params=extra_config_options)
process = subprocess.Popen(" ".join(split_command), shell=True, env=os.environ.copy())
process.wait()
