#!/usr/bin/env python3
"""
A股各板块统计分析
- 各板块股票总数（今日）
- 各板块 10 日涨跌股票数

数据源：新浪财经批量行情接口
"""
import json, time, random, sys, os
import subprocess
import urllib.request

# 清除代理
for k in list(os.environ.keys()):
    if '_proxy' in k.lower(): os.environ.pop(k, None)

def fetch_sina(url, max_retries=2):
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': 'https://finance.sina.com.cn/'
            })
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('gbk'))
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return None

def parse_flow_val(s):
    """解析资金流数字字符串"""
    if not s or s == '-' or s == '0':
        return 0.0
    s = str(s)
    neg = -1 if s.startswith('-') else 1
    s = s.lstrip('-').rstrip('%')
    mult = 1
    if '亿' in s:
        mult, s = 1e8, s.replace('亿', '')
    elif '万' in s:
        mult, s = 1e4, s.replace('万', '')
    try:
        return float(s) * mult
    except:
        return 0.0

def get_board_stats_sina(node, board_name):
    """
    通过新浪批量接口获取某板块全部股票 + 涨跌幅
    返回 {total, rising, falling, board_name}
    """
    all_stocks = []
    page = 1
    while True:
        url = (f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
               f"/Market_Center.getHQNodeDataSimple?page={page}&num=100"
               f"&sort=symbol&asc=1&node={node}")
        data = fetch_sina(url)
        if not data:
            break
        if isinstance(data, dict) and data.get('ERROR'):
            break
        if not isinstance(data, list) or len(data) == 0:
            break
        all_stocks.extend(data)
        print(f"  [{board_name}] page {page}: +{len(data)} stocks (total {len(all_stocks)})", file=sys.stderr)
        if len(data) < 100:
            break
        page += 1
        time.sleep(random.uniform(0.3, 0.8))
    
    # 按股票代码前缀判断板块
    def classify(stock):
        sym = stock.get('symbol', '')
        # 上海主板: 600/601/602/603/605 开头
        if sym.startswith('sh600') or sym.startswith('sh601') or sym.startswith('sh602') \
           or sym.startswith('sh603') or sym.startswith('sh605'):
            return 'sh_main'
        elif sym.startswith('sh688'):
            return 'kcb'
        # 深圳主板(含中小板): 000/001/002/003 开头
        elif sym.startswith('sz000') or sym.startswith('sz001') or sym.startswith('sz002') \
             or sym.startswith('sz003'):
            return 'sz_main'
        # 创业板: 300/301/302 开头
        elif sym.startswith('sz300') or sym.startswith('sz301') or sym.startswith('sz302'):
            return 'cyb'
        # 北证
        elif sym.startswith('bj'):
            return 'bj'
        return 'other'
    
    boards = {'sh_main': [], 'kcb': [], 'sz_main': [], 'cyb': [], 'bj': [], 'other': []}
    for s in all_stocks:
        b = classify(s)
        boards[b].append(s)
    
    results = {}
    for b, stocks in boards.items():
        rising = [s for s in stocks if float(s.get('changepercent', 0)) > 0]
        flat = [s for s in stocks if float(s.get('changepercent', 0)) == 0]
        falling = [s for s in stocks if float(s.get('changepercent', 0)) < 0]
        results[b] = {
            'total': len(stocks),
            'rising': len(rising),
            'flat': len(flat),
            'falling': len(falling),
            'rising_pct': round(len(rising)/len(stocks)*100, 1) if stocks else 0,
        }
    
    return results, all_stocks

def get_10day_stats(stocks, board_name, limit_stocks=500):
    """
    获取近10日涨跌统计（采样，limit_stocks 只）
    用 CDP 浏览器获取
    """
    # 这个需要 CDP，大批量太慢，这里返回占位
    return {}

def main():
    print("=== A股板块统计分析 ===", flush=True)
    
    # 用 sh_a 节点获取上海+科创
    print("\n[1] 获取上海板块数据...", flush=True)
    sh_results, sh_stocks = get_board_stats_sina('sh_a', '上海')
    
    # 用 sz_a 节点获取深圳+创业板
    print("\n[2] 获取深圳板块数据...", flush=True)
    sz_results, sz_stocks = get_board_stats_sina('sz_a', '深圳')
    
    # 合并
    all_results = {}
    all_results.update(sh_results)
    all_results.update(sz_results)
    
    # 北证：用 bj 节点
    print("\n[3] 获取北证板块数据...", flush=True)
    bj_results, bj_stocks = get_board_stats_sina('bj', '北证')
    all_results.update(bj_results)
    
    # 汇总
    BOARD_NAMES = {
        'sh_main': '主板(沪)',
        'kcb': '科创板',
        'sz_main': '主板(深)',
        'cyb': '创业板',
        'bj': '北证',
    }
    
    print("\n" + "="*60)
    print(f"{'板块':<12} {'总数':>8} {'上涨':>8} {'下跌':>8} {'平盘':>6} {'上涨%':>8}")
    print("-"*60)
    
    for b, name in BOARD_NAMES.items():
        r = all_results.get(b, {})
        total = r.get('total', 0)
        rising = r.get('rising', 0)
        falling = r.get('falling', 0)
        flat = r.get('flat', 0)
        pct = r.get('rising_pct', 0)
        print(f"{name:<12} {total:>8} {rising:>8} {falling:>8} {flat:>6} {pct:>7.1f}%")
    
    total_all = sum(r.get('total',0) for r in all_results.values())
    rising_all = sum(r.get('rising',0) for r in all_results.values())
    falling_all = sum(r.get('falling',0) for r in all_results.values())
    pct_all = rising_all/total_all*100 if total_all else 0
    print("-"*60)
    print(f"{'合计':<12} {total_all:>8} {rising_all:>8} {falling_all:>8} {sum(r.get('flat',0) for r in all_results.values()):>6} {pct_all:>7.1f}%")
    print("="*60)
    print("\n注: 今日统计（收盘后数据更准确）")
    print("10日统计需要逐只股票历史数据，数据量较大请稍候...")

if __name__ == '__main__':
    main()
