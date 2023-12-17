@echo off
cd /d %~dp0
cd ..
docker exec node /bitcoin-cli.sh generate 1
