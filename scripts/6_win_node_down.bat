@echo off
cd /d %~dp0
cd ..
docker kill node
docker stop node
docker rm node
