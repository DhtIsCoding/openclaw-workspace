#!/usr/bin/env python3
import requests, time, random, json

def fetch(url, timeout=10):
    r = requests.get(url, timeout=timeout)
    return r.json()

def sleep_rand():
    time.sleep(random.uniform(0.5, 0.7))

# Step 1: get all stocks
all_stocks = []
page = 1
while True:
    url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeDataSimple?page={page}&num=100&sort=symbol&asc=1&node=sh_a"
    data = fetch(url)
    if not data: break
    all_stocks.extend(data)
    print(f"page {page}: {len(data)} stocks, total: {len(all_stocks)}")
    if len(data) < 100: break
    page += 1
    time.sleep(0.3)

# Step 2: filter sh_main
prefixes = ('sh600','sh601','sh602','sh603','sh605')
sh_main = sorted([s for s in all_stocks if s['symbol'].lower().startswith(prefixes)], key=lambda x: x['symbol'])[:50]
print(f"sh_main count: {len(sh_main)}")

# Step 3-4: kline data
result = {"board":"sh_main","total":50,"rising":0,"failed":0,"stocks":[]}
for i, s in enumerate(sh_main):
    sym = s['symbol'].lower()
    kline = None
    for attempt in range(3):
        try:
            url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=5&datalen=11"
            kline = fetch(url)
            if kline: break
        except:
            pass
        time.sleep(random.uniform(0.5, 0.7))
    
    if not kline or len(kline) < 10:
        result["failed"] += 1
        result["stocks"].append({"symbol": sym, "up": False})
        print(f"[{i+1}/50] {sym} FAILED")
    else:
        try:
            first_close = float(kline[0]['close'])
            last_close = float(kline[-1]['close'])
            up = last_close > first_close
            if up: result["rising"] += 1
            result["stocks"].append({"symbol": sym, "up": up})
            print(f"[{i+1}/50] {sym}: {first_close} -> {last_close}, up={up}")
        except:
            result["failed"] += 1
            result["stocks"].append({"symbol": sym, "up": False})
            print(f"[{i+1}/50] {sym} PARSE_ERROR")
    sleep_rand()

print("RESULT_START")
print(json.dumps(result, ensure_ascii=False))
print("RESULT_END")
