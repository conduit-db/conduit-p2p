@echo off
cd /d %~dp0
cd ..
docker build -t conduit-p2p -f ./scripts/Dockerfile --no-cache . || exit /b
docker run conduit-p2p ./scripts/docker_run_static_checks.sh
