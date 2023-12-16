@echo off
cd /d %~dp0
cd ..
docker build -t node-image -f ./contrib/node/Dockerfile .
docker run -d --name node -p 18332:18332 -p 18444:18444 node-image
