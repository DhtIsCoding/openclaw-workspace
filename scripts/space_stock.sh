#!/bin/bash
# 商业航天板块实时数据快捷调用
# 用法: bash space_stock.sh [mode]
#   mode=report    → 输出完整报告（默认）
#   mode=top10     → 输出资金流入前十
#   mode=price     → 输出个股价格（需指定 CODE env）

python3 /home/dht/.openclaw/workspace/scripts/space_stock_collector.py 2>&1
