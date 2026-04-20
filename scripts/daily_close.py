#!/usr/bin/env python3
"""
daily_close.py — A股每日收盘价增量采集
用法: python3 daily_close.py
每次运行记录当天收盘价，运行10天后自动拥有完整10日统计数据
"""
import os, json, sqlite3, urllib.request, time, random, sys
from datetime import datetime

# 清除代理环境变量
for k in list(os.environ.keys()):
    if '_proxy' in k.lower():
        os.environ.pop(k, None)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'daily_close.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS daily_close (
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            close REAL,
            change_pct REAL,
            PRIMARY KEY (symbol, trade_date)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS board_class (
            symbol TEXT PRIMARY KEY,
            board TEXT NOT NULL
        )
    ''')
    conn.commit()
    return conn

def classify(symbol):
    if symbol.startswith('sh600') or symbol.startswith('sh601') or symbol.startswith('sh602') \
       or symbol.startswith('sh603') or symbol.startswith('sh605'): return 'sh_main'
    elif symbol.startswith('sh688'): return 'kcb'
    elif symbol.startswith('sz000') or symbol.startswith('sz001') \
         or symbol.startswith('sz002') or symbol.startswith('sz003'): return 'sz_main'
    elif symbol.startswith('sz300') or symbol.startswith('sz301') \
         or symbol.startswith('sz302'): return 'cyb'
    elif symbol.startswith('bj'): return 'bj'
    return 'other'

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': 'https://finance.sina.com.cn/'
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('gbk', errors='replace'))

def fetch_all_stocks():
    """获取今日所有A股列表"""
    all_stocks = []
    for page in range(1, 80):
        url = (f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php'
               f'/Market_Center.getHQNodeDataSimple?page={page}&num=100'
               f'&sort=symbol&asc=1&node=hs_a')
        try:
            data = fetch(url)
            if not data or len(data) == 0: break
            for s in data:
                sym = s.get('symbol', '')
                if not sym or classify(sym) == 'other': continue
                all_stocks.append({
                    'symbol': sym,
                    'close': float(s.get('trade', 0) or 0),
                    'change_pct': float(s.get('changepercent', 0) or 0),
                    'board': classify(sym)
                })
            if len(data) < 100: break
            time.sleep(random.uniform(0.25, 0.4))
        except Exception as e:
            print(f'  [W] page {page} error: {e}', flush=True)
            break
    return all_stocks

def save_to_db(conn, stocks, trade_date):
    """保存今日数据到数据库"""
    cursor = conn.cursor()
    saved = 0
    for s in stocks:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO daily_close (symbol, trade_date, close, change_pct)
                VALUES (?, ?, ?, ?)
            ''', (s['symbol'], trade_date, s['close'], s['change_pct']))
            saved += 1
        except Exception as e:
            print(f'  [W] insert {s["symbol"]} error: {e}', flush=True)
    
    # 保存板块分类
    for s in stocks:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO board_class (symbol, board)
                VALUES (?, ?)
            ''', (s['symbol'], s['board']))
        except: pass
    
    conn.commit()
    return saved

def compute_10day_stats(conn):
    """计算近10日统计数据"""
    cursor = conn.cursor()
    trade_dates = [row[0] for row in cursor.execute(
        'SELECT DISTINCT trade_date FROM daily_close ORDER BY trade_date DESC LIMIT 10'
    ).fetchall()]
    
    if len(trade_dates) < 2:
        return None, f'数据不足：仅 {len(trade_dates)} 天，需要至少2天才能计算涨跌'
    
    first_date = trade_dates[-1]  # 最早的一天
    last_date = trade_dates[0]    # 最近的一天
    
    boards = {'sh_main': '主板(沪)', 'kcb': '科创板', 'sz_main': '主板(深)', 'cyb': '创业板', 'bj': '北证'}
    results = []
    
    print(f'\n近10日统计数据（{first_date} ~ {last_date}，共{len(trade_dates)}天）:', flush=True)
    print(f'{"板块":<10} {"总数":>6} {"10日上涨":>8} {"10日下跌":>8} {"上涨占比":>8}', flush=True)
    print('-' * 45, flush=True)
    
    total_all, rising_all, falling_all = 0, 0, 0
    
    for board_code, board_name in boards.items():
        # 该板块所有股票
        cursor.execute('SELECT symbol FROM board_class WHERE board = ?', (board_code,))
        symbols = [row[0] for row in cursor.fetchall()]
        total = len(symbols)
        
        rising, falling = 0, 0
        for sym in symbols:
            # 获取该股最早日和最后一日收盘价
            cursor.execute('''
                SELECT close FROM daily_close 
                WHERE symbol = ? AND trade_date IN (?, ?)
                ORDER BY trade_date ASC
            ''', (sym, first_date, last_date))
            rows = cursor.fetchall()
            if len(rows) >= 2 and rows[0][0] and rows[-1][0]:
                if rows[-1][0] > rows[0][0]:
                    rising += 1
                else:
                    falling += 1
        
        pct = rising / total * 100 if total > 0 else 0
        results.append({'board': board_name, 'total': total, 'rising': rising, 'falling': falling, 'pct': pct})
        total_all += total
        rising_all += rising
        falling_all += falling
        print(f'{board_name:<10} {total:>6} {rising:>8} {falling:>8} {pct:>7.1f}%', flush=True)
    
    print('-' * 45, flush=True)
    total_pct = rising_all / total_all * 100 if total_all > 0 else 0
    print(f'{"合计":<10} {total_all:>6} {rising_all:>8} {falling_all:>8} {total_pct:>7.1f}%', flush=True)
    
    return results, None

def main():
    today = get_today_str()
    conn = init_db()
    
    # 检查今日是否已采集
    cursor = conn.cursor()
    existing = cursor.execute(
        'SELECT COUNT(*) FROM daily_close WHERE trade_date = ?', (today,)
    ).fetchone()[0]
    
    if existing > 0:
        print(f'[{today}] 今日数据已存在（{existing}只），跳过采集，直接计算统计', flush=True)
    else:
        print(f'[{today}] 开始采集今日A股数据...', flush=True)
        stocks = fetch_all_stocks()
        print(f'获取到 {len(stocks)} 只股票，开始写入数据库...', flush=True)
        saved = save_to_db(conn, stocks, today)
        print(f'写入完成：{saved} 只', flush=True)
    
    # 计算统计
    results, err = compute_10day_stats(conn)
    if err:
        print(f'\n注意: {err}，继续每日运行，数据会逐渐积累', flush=True)
    
    conn.close()
    return results

if __name__ == '__main__':
    main()
