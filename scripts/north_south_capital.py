#!/usr/bin/env python3
"""
north_south_capital.py — 沪深港通资金流向采集
通过 Playwright 访问 EastMoney 沪深港通页面，获取北向/南向资金数据
用法: python3 north_south_capital.py
"""
import os, sys, json, sqlite3, re
from datetime import datetime
from pathlib import Path

# Playwright（WSL2 内置 Chromium）
import playwright

DB_PATH = Path(__file__).parent.parent / 'data' / 'daily_close.db'
os.makedirs(DB_PATH.parent, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS north_south_capital (
            trade_date TEXT NOT NULL,
            direction TEXT NOT NULL,  -- 'north_hgt' / 'north_sgt' / 'south_hgt' / 'south_sgt'
            net_amount REAL,          -- 净买额（亿元）
            total_amount REAL,        -- 成交总额（亿元）
            buy_amount REAL,          -- 买入额（亿元）
            sell_amount REAL,         -- 卖出额（亿元）
            leader_stock TEXT,        -- 领涨股
            PRIMARY KEY (trade_date, direction)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS hsgt_top10 (
            trade_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            direction TEXT NOT NULL,  -- 'hgt' / 'sgt' / 'hgt_south' / 'sgt_south'
            symbol TEXT,
            name TEXT,
            close REAL,
            change_pct REAL,
            amount REAL,             -- 成交额（亿元）
            pe REAL,
            market_cap REAL,          -- 总市值（亿元）
            PRIMARY KEY (trade_date, direction, rank)
        )
    ''')
    conn.commit()
    return conn

def parse_amount(text):
    """解析 '1289.76亿元' -> 1289.76"""
    if not text or text in ['--', '-', '']:
        return None
    m = re.search(r'([-\d.]+)', text)
    if m:
        val = float(m.group(1))
        if '万' in text:
            val /= 10000
        return val
    return None

def fetch_page():
    """通过 Playwright 获取沪深港通页面"""
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        
        page.goto('https://data.eastmoney.com/hsgtcg/', 
                  wait_until='domcontentloaded', timeout=20000)
        page.wait_for_timeout(4000)  # 等待JS渲染
        
        text = page.evaluate('document.body.innerText')
        html = page.content()
        
        browser.close()
        return text, html

def parse_capital_data(text, html):
    """解析北向/南向资金数据"""
    results = {}
    
    # 提取日期
    date_match = re.search(r'数据日期[：:]\s*(\d{4}-\d{2}-\d{2})', text)
    trade_date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
    
    # 北向资金 - 成交总额
    # 沪股通 成交总额
    m = re.search(r'沪股通.*?成交总额.*?([-\d.]+)\s*亿', text)
    north_hgt_total = float(m.group(1)) if m else None
    
    # 深股通 成交总额
    m = re.search(r'深股通.*?成交总额.*?([-\d.]+)\s*亿', text)
    north_sgt_total = float(m.group(1)) if m else None
    
    # 北向合计
    m = re.search(r'北向资金.*?成交总额.*?([-\d.]+)\s*亿', text)
    north_total = float(m.group(1)) if m else None
    
    # 南向资金 - 净买额
    m = re.search(r'港股通\(沪\).*?净买额.*?([-\d.]+)亿', text)
    south_hgt_net = float(m.group(1)) if m else None
    
    m = re.search(r'港股通\(深\).*?净买额.*?([-\d.]+)亿', text)
    south_sgt_net = float(m.group(1)) if m else None
    
    m = re.search(r'南向资金.*?净买额.*?([-\d.]+)亿', text)
    south_total_net = float(m.group(1)) if m else None
    
    # 领涨股
    m = re.search(r'沪股通.*?领涨股\s+(\S+)', text)
    north_hgt_leader = m.group(1) if m else None
    
    m = re.search(r'深股通.*?领涨股\s+(\S+)', text)
    north_sgt_leader = m.group(1) if m else None
    
    # 买入/卖出额（南向）
    m = re.search(r'港股通\(沪\).*?买入额\s*([-\d.]+)亿', text)
    south_hgt_buy = float(m.group(1)) if m else None
    
    m = re.search(r'港股通\(沪\).*?卖出额\s*([-\d.]+)亿', text)
    south_hgt_sell = float(m.group(1)) if m else None
    
    m = re.search(r'港股通\(深\).*?买入额\s*([-\d.]+)亿', text)
    south_sgt_buy = float(m.group(1)) if m else None
    
    m = re.search(r'港股通\(深\).*?卖出额\s*([-\d.]+)亿', text)
    south_sgt_sell = float(m.group(1)) if m else None
    
    results['trade_date'] = trade_date
    results['north'] = {
        'hgt_total': north_hgt_total,
        'sgt_total': north_sgt_total,
        'total': north_total,
        'hgt_leader': north_hgt_leader,
        'sgt_leader': north_sgt_leader,
    }
    results['south'] = {
        'hgt_net': south_hgt_net,
        'sgt_net': south_sgt_net,
        'total_net': south_total_net,
        'hgt_buy': south_hgt_buy,
        'hgt_sell': south_hgt_sell,
        'sgt_buy': south_sgt_buy,
        'sgt_sell': south_sgt_sell,
    }
    
    return results, trade_date

def parse_top10(html, trade_date):
    """解析十大成交股"""
    stocks = []
    
    # 解析沪股通十大成交股表格
    # 格式: 排名 代码 名称 ... 收盘价 涨跌幅 成交额 市盈率 总市值
    pattern = r'<td[^>]*>\s*(\d+)\s*</td>\s*<td[^>]*>\s*(\d{6})\s*</td>\s*<td[^>]*>\s*([^<]+)\s*</td>.*?<td[^>]*>\s*([-\d.]+)%\s*</td>.*?<td[^>]*>\s*([-\d.]+)亿\s*</td>'
    
    # 简化解析：从HTML提取十大成交股
    hgt_stocks = re.findall(r'沪股通十大成交股.*?<td[^>]*>\s*(\d{6})\s*</td>.*?<td[^>]*>\s*([^<]+)\s*</td>.*?>([^-]+)>([-\d.]+)%.*?([-\d.]+)亿', html, re.DOTALL)
    
    return stocks

def save_to_db(conn, data, trade_date):
    """保存到数据库"""
    c = conn.cursor()
    
    # 北向资金
    c.execute('''
        INSERT OR REPLACE INTO north_south_capital 
        (trade_date, direction, total_amount, net_amount, leader_stock)
        VALUES (?, ?, ?, ?, ?)
    ''', (trade_date, 'north_hgt', data['north']['hgt_total'], None, data['north']['hgt_leader']))
    
    c.execute('''
        INSERT OR REPLACE INTO north_south_capital 
        (trade_date, direction, total_amount, leader_stock)
        VALUES (?, ?, ?, ?)
    ''', (trade_date, 'north_sgt', data['north']['sgt_total'], data['north']['sgt_leader']))
    
    # 南向资金
    c.execute('''
        INSERT OR REPLACE INTO north_south_capital 
        (trade_date, direction, net_amount, buy_amount, sell_amount)
        VALUES (?, ?, ?, ?, ?)
    ''', (trade_date, 'south_hgt', data['south']['hgt_net'], data['south']['hgt_buy'], data['south']['hgt_sell']))
    
    c.execute('''
        INSERT OR REPLACE INTO north_south_capital 
        (trade_date, direction, net_amount, buy_amount, sell_amount)
        VALUES (?, ?, ?, ?, ?)
    ''', (trade_date, 'south_sgt', data['south']['sgt_net'], data['south']['sgt_buy'], data['south']['sgt_sell']))
    
    conn.commit()

def main():
    print('[北向/南向资金] 开始采集...', flush=True)
    
    try:
        text, html = fetch_page()
    except Exception as e:
        print(f'[错误] 页面加载失败: {e}')
        sys.exit(1)
    
    data, trade_date = parse_capital_data(text, html)
    
    print(f'数据日期: {trade_date}', flush=True)
    print(f'北向资金:', flush=True)
    print(f'  沪股通成交总额: {data["north"]["hgt_total"]}亿元  领涨股: {data["north"]["hgt_leader"]}', flush=True)
    print(f'  深股通成交总额: {data["north"]["sgt_total"]}亿元  领涨股: {data["north"]["sgt_leader"]}', flush=True)
    print(f'  北向合计: {data["north"]["total"]}亿元', flush=True)
    print(f'南向资金:', flush=True)
    print(f'  港股通(沪)净买额: {data["south"]["hgt_net"]}亿  买入:{data["south"]["hgt_buy"]}亿 卖出:{data["south"]["hgt_sell"]}亿', flush=True)
    print(f'  港股通(深)净买额: {data["south"]["sgt_net"]}亿  买入:{data["south"]["sgt_buy"]}亿 卖出:{data["south"]["sgt_sell"]}亿', flush=True)
    print(f'  南向合计净买额: {data["south"]["total_net"]}亿', flush=True)
    
    conn = init_db()
    save_to_db(conn, data, trade_date)
    conn.close()
    
    print(f'[完成] 已保存至数据库', flush=True)
    return data

if __name__ == '__main__':
    main()
