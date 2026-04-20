#!/usr/bin/env python3
"""save_capital.py — 保存北向/南向资金数据到数据库"""
import sqlite3, sys, json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'daily_close.db'

data = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
trade_date = data.get('tradeDate')
records = data.get('records', [])

conn = sqlite3.connect(DB_PATH)
conn.execute('''
    CREATE TABLE IF NOT EXISTS north_south_capital (
        trade_date TEXT NOT NULL, direction TEXT NOT NULL,
        net_amount REAL, total_amount REAL, buy_amount REAL, sell_amount REAL, leader_stock TEXT,
        PRIMARY KEY (trade_date, direction)
    )
''')
for r in records:
    conn.execute('''
        INSERT OR REPLACE INTO north_south_capital 
        (trade_date, direction, net_amount, total_amount, buy_amount, sell_amount, leader_stock)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (trade_date, r['direction'], r.get('net'), r.get('total'), 
          r.get('buy'), r.get('sell'), r.get('leader')))
conn.commit()
conn.close()
print('OK')
