#!/usr/bin/env python3
"""
tushare_daily.py — 全市场日线数据采集器
支持：断点续传 + 增量更新 + 频率控制

用法：
    python3 tushare_daily.py              # 增量采集（默认5天）
    python3 tushare_daily.py --days 10    # 增量采集10天
    python3 tushare_daily.py --full       # 全量历史采集
    python3 tushare_daily.py --status     # 查看状态
"""

import os
import sys
import json
import time
import random
import sqlite3
import logging
import signal
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# 清除代理
for k in list(os.environ.keys()):
    if '_proxy' in k.lower():
        os.environ.pop(k, None)

# ===================== 配置 =====================
WORKSPACE = Path("/home/dht/.openclaw/workspace")
DATA_DIR = WORKSPACE / "data"
DB_PATH = DATA_DIR / "tushare_daily.db"
TOKEN_FILE = WORKSPACE / ".tushare_token"
LOG_FILE = DATA_DIR / "tushare_daily.log"

BATCH_SIZE = 50          # 每批50只股票
RATE_LIMIT = 40          # 每分钟40次（留10次余量）
RATE_PERIOD = 60         # 1分钟窗口
MAX_DAILY = 8000         # 每日上限

# ===================== 日志 =====================
logger = logging.getLogger("tushare_daily")


def setup_logging():
    """配置日志"""
    DATA_DIR.mkdir(exist_ok=True)
    
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 文件日志
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
    fh.setFormatter(formatter)
    
    # 控制台日志
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(ch)


# ===================== 数据库 =====================
def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    return sqlite3.connect(DB_PATH, timeout=30)


def init_db():
    """初始化数据库"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_basic (
            ts_code TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            board TEXT,
            list_date TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            vol REAL,
            amount REAL,
            PRIMARY KEY (ts_code, trade_date)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS fetch_progress (
            ts_code TEXT PRIMARY KEY,
            last_trade_date TEXT,
            last_fetch_time TEXT,
            fetch_count INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            stat_date TEXT PRIMARY KEY,
            total_calls INTEGER DEFAULT 0,
            stocks_updated INTEGER DEFAULT 0,
            records_written INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # 索引
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_date ON daily(trade_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_code ON daily(ts_code)')
    
    conn.commit()
    return conn


# ===================== Token =====================
def get_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    token = os.environ.get("TUSHARE_TOKEN", "")
    if token:
        return token
    raise ValueError("未找到 Tushare token")


# ===================== Sina API: 股票列表 =====================
def fetch_sina_stock_list() -> list:
    """通过 Sina 获取全市场股票列表"""
    all_stocks = []
    page = 1
    
    while True:
        url = (
            f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php'
            f'/Market_Center.getHQNodeDataSimple?page={page}&num=100'
            f'&sort=symbol&asc=1&node=hs_a'
        )
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': 'https://finance.sina.com.cn/'
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode('gbk', errors='replace'))
        except Exception as e:
            logger.warning(f"Sina page {page} error: {e}")
            break
        
        if not data:
            break
            
        for s in data:
            symbol = s.get('symbol', '')
            if symbol.startswith('sh6') and not symbol.startswith('sh688'):
                ts_code = symbol[2:] + '.SH'
                board = 'sh_main'
            elif symbol.startswith('sh688'):
                ts_code = symbol[2:] + '.SH'
                board = 'kcb'
            elif symbol.startswith(('sz000', 'sz001')):
                ts_code = symbol[2:] + '.SZ'
                board = 'sz_main'
            elif symbol.startswith(('sz300', 'sz301', 'sz302')):
                ts_code = symbol[2:] + '.SZ'
                board = 'cyb'
            elif symbol.startswith('bj9'):
                ts_code = symbol[2:] + '.BJ'
                board = 'bj'
            else:
                continue
            
            all_stocks.append({
                'ts_code': ts_code,
                'symbol': symbol,
                'name': s.get('name', ''),
                'board': board
            })
        
        if len(data) < 100:
            break
        page += 1
        time.sleep(random.uniform(0.2, 0.4))
    
    return all_stocks


def sync_stock_list(force: bool = False) -> list:
    """同步股票列表"""
    conn = init_db()
    c = conn.cursor()
    
    if not force:
        cached = c.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
        if cached >= 1000:
            logger.info(f"股票列表已有 {cached} 只，使用缓存")
            stocks = [r[0] for r in c.execute("SELECT ts_code FROM stock_basic").fetchall()]
            conn.close()
            return stocks
    
    logger.info("通过 Sina API 获取股票列表...")
    stocks_data = fetch_sina_stock_list()
    
    if not stocks_data:
        logger.warning("Sina 获取失败，使用缓存")
        stocks = [r[0] for r in c.execute("SELECT ts_code FROM stock_basic").fetchall()]
        conn.close()
        return stocks
    
    c.execute("DELETE FROM stock_basic")
    for s in stocks_data:
        c.execute('''
            INSERT INTO stock_basic (ts_code, symbol, name, board)
            VALUES (?, ?, ?, ?)
        ''', (s['ts_code'], s['symbol'], s['name'], s['board']))
    
    c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('stock_list_updated', ?)",
              (datetime.now().isoformat(),))
    conn.commit()
    conn.close()
    
    stocks = [s['ts_code'] for s in stocks_data]
    logger.info(f"股票列表同步完成: {len(stocks)} 只")
    return stocks


# ===================== Tushare API =====================
class TushareAPI:
    def __init__(self, token: str):
        import tushare as ts
        ts.set_token(token)
        self.pro = ts.pro_api()
        self._call_count = 0
        self._minute_start = time.time()
        self._calls_this_minute = 0
        self._last_call_time = 0
        logger.info("Tushare API 初始化成功")
    
    def _reset_counter(self):
        now = time.time()
        if now - self._minute_start >= RATE_PERIOD:
            self._minute_start = now
            self._calls_this_minute = 0
    
    def _rate_limit_wait(self):
        self._reset_counter()
        if self._calls_this_minute >= RATE_LIMIT:
            sleep_time = RATE_PERIOD - (time.time() - self._minute_start)
            if sleep_time > 0:
                logger.info(f"频率限制，等待 {sleep_time:.1f}s")
                time.sleep(sleep_time)
                self._reset_counter()
    
    def _handle_rate_limit_error(self, error_msg: str):
        """处理频率限制错误，等待超过1分钟后重试"""
        logger.warning(f"Rate limit error: {error_msg[:50]}...")
        logger.info("等待 65 秒后重试...")
        time.sleep(65)
        self._reset_counter()
        self._minute_start = time.time() - RATE_PERIOD + 1  # 确保下一秒可以调用
    
    def call(self, method: str, **kwargs):
        """调用 Tushare API，带频率控制"""
        self._rate_limit_wait()
        
        try:
            func = getattr(self.pro, method)
            result = func(**kwargs)
            self._calls_this_minute += 1
            self._call_count += 1
            
            # 随机延时
            time.sleep(random.uniform(0.5, 0.8))
            return result
        except Exception as e:
            err_msg = str(e)
            if '每分钟' in err_msg or '50次' in err_msg:
                self._handle_rate_limit_error(err_msg)
                return self.call(method, **kwargs)  # 重试
            logger.error(f"Tushare.{method} 失败: {e}")
            return None
    
    @property
    def call_count(self) -> int:
        return self._call_count


# ===================== 采集逻辑 =====================
def batch_fetch(api: TushareAPI, ts_codes: list, start_date: str, end_date: str) -> list:
    """批量获取日线数据"""
    if not ts_codes:
        return []
    
    ts_str = ",".join(ts_codes)
    df = api.call("daily", ts_code=ts_str, start_date=start_date, end_date=end_date)
    
    if df is None or len(df) == 0:
        return []
    
    records = []
    for _, row in df.iterrows():
        records.append({
            'ts_code': row['ts_code'],
            'trade_date': str(row['trade_date']),
            'open': row.get('open'),
            'high': row.get('high'),
            'low': row.get('low'),
            'close': row.get('close'),
            'vol': row.get('vol'),
            'amount': row.get('amount'),
        })
    return records


def save_records(conn: sqlite3.Connection, records: list) -> int:
    """保存记录"""
    if not records:
        return 0
    saved = 0
    for r in records:
        try:
            conn.execute('''
                INSERT OR REPLACE INTO daily 
                (ts_code, trade_date, open, high, low, close, vol, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (r['ts_code'], r['trade_date'], r['open'], r['high'],
                  r['low'], r['close'], r['vol'], r['amount']))
            saved += 1
        except:
            pass
    conn.commit()
    return saved


def update_progress(conn: sqlite3.Connection, ts_code: str, trade_date: str):
    """更新进度"""
    conn.execute('''
        INSERT OR REPLACE INTO fetch_progress (ts_code, last_trade_date, last_fetch_time, fetch_count)
        VALUES (?, ?, ?, COALESCE((SELECT fetch_count FROM fetch_progress WHERE ts_code = ?), 0) + 1)
    ''', (ts_code, trade_date, datetime.now().isoformat(), ts_code))


def record_stats(conn: sqlite3.Connection, calls: int, stocks: int, records: int):
    """记录统计"""
    today = datetime.now().strftime('%Y-%m-%d')
    conn.execute('''
        INSERT INTO daily_stats (stat_date, total_calls, stocks_updated, records_written)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(stat_date) DO UPDATE SET
            total_calls = total_calls + excluded.total_calls,
            stocks_updated = stocks_updated + excluded.stocks_updated,
            records_written = records_written + excluded.records_written
    ''', (today, calls, stocks, records))
    conn.commit()


# ===================== 主采集 =====================
def run_incremental(days: int = 5, token: str = None):
    """增量采集"""
    if token is None:
        token = get_token()
    
    api = TushareAPI(token)
    conn = init_db()
    
    # 获取股票列表
    stocks = sync_stock_list()
    total_stocks = len(stocks)
    
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    
    logger.info(f"增量采集: {start_date} ~ {end_date}, {total_stocks} 只股票")
    
    batches = [stocks[i:i+BATCH_SIZE] for i in range(0, total_stocks, BATCH_SIZE)]
    total_calls = 0
    total_records = 0
    
    # 进度文件（支持中断恢复）
    progress_file = DATA_DIR / "collection_progress.json"
    try:
        with open(progress_file) as f:
            progress = json.load(f)
    except:
        progress = {"batch_index": 0, "batch_offset": {}}
    
    for batch_idx in range(progress["batch_index"], len(batches)):
        batch = batches[batch_idx]
        
        records = batch_fetch(api, batch, start_date, end_date)
        total_calls += 1
        
        if records:
            saved = save_records(conn, records)
            total_records += saved
            
            max_date = max(r['trade_date'] for r in records)
            for ts_code in batch:
                update_progress(conn, ts_code, max_date)
        
        # 每10批显示进度
        if (batch_idx + 1) % 10 == 0:
            logger.info(f"进度 [{batch_idx+1}/{len(batches)}] "
                        f"调用 {total_calls}, 记录 {total_records}")
        
        # 保存进度
        progress["batch_index"] = batch_idx + 1
        with open(progress_file, 'w') as f:
            json.dump(progress, f)
    
    # 清理进度文件
    if progress_file.exists():
        progress_file.unlink()
    
    record_stats(conn, total_calls, total_stocks, total_records)
    conn.close()
    
    logger.info("=" * 50)
    logger.info(f"增量采集完成: {total_calls} 调用, {total_records} 记录")
    
    return total_calls, total_records


def show_status():
    """显示状态"""
    conn = init_db()
    c = conn.cursor()
    
    today_str = datetime.now().strftime('%Y%m%d')
    
    print("\n" + "=" * 50)
    print("Tushare 日线采集状态")
    print("=" * 50)
    
    stock_count = c.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
    print(f"股票列表: {stock_count} 只")
    
    daily_count = c.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    daily_dates = c.execute("SELECT COUNT(DISTINCT trade_date) FROM daily").fetchone()[0]
    print(f"历史数据: {daily_count} 条, {daily_dates} 个交易日")
    
    progress_count = c.execute("SELECT COUNT(*) FROM fetch_progress").fetchone()[0]
    print(f"已跟踪: {progress_count} 只")
    
    # 今日数据
    today_count = c.execute(
        "SELECT COUNT(DISTINCT ts_code) FROM daily WHERE trade_date = ?", (today_str,)
    ).fetchone()[0]
    print(f"今日({today_str}): {today_count} 只")
    
    # 每日统计
    print("\n每日统计:")
    stats = c.execute('''
        SELECT stat_date, total_calls, stocks_updated, records_written
        FROM daily_stats ORDER BY stat_date DESC LIMIT 7
    ''').fetchall()
    for s in stats:
        print(f"  {s[0]}: {s[1]}调用, {s[2]}股, {s[3]}条")
    
    # 最近日期分布
    print("\n最近日期覆盖:")
    recent = c.execute('''
        SELECT trade_date, COUNT(*) 
        FROM daily 
        GROUP BY trade_date 
        ORDER BY trade_date DESC 
        LIMIT 5
    ''').fetchall()
    for r in recent:
        print(f"  {r[0]}: {r[1]} 只")
    
    conn.close()


# ===================== 信号处理 =====================
shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    logger.info("收到中断信号，保存进度...")
    shutdown_requested = True


if __name__ == "__main__":
    import argparse
    
    setup_logging()
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(description="Tushare 日线采集")
    parser.add_argument("--days", type=int, default=5, help="增量天数")
    parser.add_argument("--force-stocks", action="store_true", help="强制更新股票列表")
    parser.add_argument("--status", action="store_true", help="仅显示状态")
    args = parser.parse_args()
    
    try:
        if args.status:
            show_status()
        else:
            sync_stock_list(force=args.force_stocks)
            run_incremental(days=args.days)
            show_status()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"错误: {e}")
        raise
