@echo off
cd /d %~dp0
cd ..
docker stop node
docker rm node
