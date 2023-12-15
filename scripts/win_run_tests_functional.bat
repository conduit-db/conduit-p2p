@echo off
cd /d %~dp0
cd ..
docker build -t conduit-p2p -f ./scripts/Dockerfile --no-cache . || exit /b
call ./scripts/win_node_up.bat
docker run conduit-p2p ./scripts/docker_run_tests_functional.sh
call ./scripts/win_node_down.bat
