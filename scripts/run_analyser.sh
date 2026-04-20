#!/bin/bash
# 清除所有代理变量后运行
unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy
export no_proxy=""
cd /home/dht/.openclaw/workspace
python3 scripts/stock_analyser.py "$@"
