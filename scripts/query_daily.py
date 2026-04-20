#!/usr/bin/env python3
"""
query_daily.py — 日线数据查询工具
用法: python3 query_daily.py 000001.SZ
      python3 query_daily.py --stats
      python3 query_daily.py --random 5
"""

import sqlite3
import sys
import random
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/home/dht/.openclaw/workspace/data/tushare_daily.db")


def get_db():
    return sqlite3.connect(DB_PATH)


def query_stock(ts_code: str, days: int = 10):
    """查询某股票最近 N 天数据"""
    conn = get_db()
    c = conn.cursor()
    
    rows = c.execute('''
        SELECT * FROM daily 
        WHERE ts_code = ?
        ORDER BY trade_date DESC 
        LIMIT ?
    ''', (ts_code, days)).fetchall()
    
    if not rows:
        print(f"未找到 {ts_code} 的数据")
        conn.close()
        return
    
    # 获取股票名称
    name_row = c.execute("SELECT name FROM stock_basic WHERE ts_code = ?", (ts_code,)).fetchone()
    name = name_row[0] if name_row else "未知"
    
    print(f"\n{'='*60}")
    print(f"{name} ({ts_code}) - 最近 {len(rows)} 个交易日")
    print(f"{'='*60}")
    print(f"{'日期':<12} {'开盘':>10} {'最高':>10} {'最低':>10} {'收盘':>10} {'成交量':>15}")
    print("-" * 60)
    
    for r in rows:
        trade_date = r[1]
        open_, high, low, close = r[2], r[3], r[4], r[5]
        vol = r[6] if r[6] else 0
        
        # 计算涨跌
        if len(rows) > 1:
            idx = rows.index(r)
            if idx < len(rows) - 1:
                prev_close = rows[idx + 1][5]
                change = close - prev_close if prev_close else 0
                change_str = f"{change:+.2f}"
            else:
                change_str = "-"
        else:
            change_str = "-"
        
        print(f"{trade_date:<12} {open_:>10.2f} {high:>10.2f} {low:>10.2f} {close:>10.2f} {vol:>15.2f} {change_str}")
    
    conn.close()


def show_stats():
    """显示统计信息"""
    conn = get_db()
    c = conn.cursor()
    
    print(f"\n{'='*60}")
    print("数据统计")
    print(f"{'='*60}")
    
    stock_count = c.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
    print(f"股票数量: {stock_count}")
    
    daily_count = c.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    daily_dates = c.execute("SELECT COUNT(DISTINCT trade_date) FROM daily").fetchone()[0]
    print(f"日线记录: {daily_count} 条")
    print(f"交易日数: {daily_dates} 天")
    
    print(f"\n每日覆盖:")
    recent = c.execute('''
        SELECT trade_date, COUNT(*) 
        FROM daily 
        GROUP BY trade_date 
        ORDER BY trade_date DESC 
    ''').fetchall()
    
    for date, cnt in recent:
        pct = cnt * 100 / stock_count
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {date}: {bar} {pct:.1f}% ({cnt})")
    
    conn.close()


def random_stocks(n: int = 5):
    """随机查看 N 只股票"""
    conn = get_db()
    c = conn.cursor()
    
    stocks = c.execute("SELECT ts_code FROM stock_basic ORDER BY RANDOM() LIMIT ?", (n,)).fetchall()
    
    for stock in stocks:
        ts_code = stock[0]
        query_stock(ts_code, days=5)
    
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    if sys.argv[1] == "--stats":
        show_stats()
    elif sys.argv[1] == "--random":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        random_stocks(n)
    elif sys.argv[1] == "--help":
        print(__doc__)
    else:
        ts_code = sys.argv[1]
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        query_stock(ts_code, days)
