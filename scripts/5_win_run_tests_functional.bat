@echo off
cd /d %~dp0
cd ..
call scripts/win_node_up.bat
py -m pytest tests_functional -v
call scripts/win_node_down.bat
