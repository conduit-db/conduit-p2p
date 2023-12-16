@echo off
cd /d %~dp0
cd ..
py ./scripts/import_blocks.py %cd%/contrib/blockchains/blockchain_116_7c9cd2