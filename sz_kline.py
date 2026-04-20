import urllib.request
import json
import time
import random

def fetch(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode('gbk', errors='replace')
                return json.loads(data)
        except Exception as e:
            if attempt >= retries:
                return None
            time.sleep(0.5 * (attempt + 1))
    return None

# Step 1: Get full Shenzhen A-share list
all_stocks = []
page = 1
while True:
    url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeDataSimple?page={page}&num=100&sort=symbol&asc=1&node=sz_a"
    data = fetch(url)
    if not data:
        break
    if len(data) < 100:
        all_stocks.extend(data)
        break
    all_stocks.extend(data)
    page += 1
    time.sleep(0.3)

print(f"Total stocks fetched: {len(all_stocks)}")

# Step 2: Filter sz000/sz001/sz002/sz003, sort, take top 50
prefixes = ('sz000', 'sz001', 'sz002', 'sz003')
filtered = [s for s in all_stocks if any(s['symbol'].lower().startswith(p) for p in prefixes)]
filtered.sort(key=lambda x: x['symbol'])
top50 = filtered[:50]
print(f"Filtered main board: {len(top50)}")

# Step 3 & 4: Get K-line data, check if rose
stocks_result = []
failed = 0
rising = 0

for s in top50:
    sym = s['symbol'].lower()
    kurl = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=5&datalen=11"
    kdata = fetch(kurl)
    if not kdata or len(kdata) < 10:
        failed += 1
        continue
    try:
        first_close = float(kdata[0]['close'])
        last_close = float(kdata[-1]['close'])
        up = last_close > first_close
        if up:
            rising += 1
        stocks_result.append({"symbol": sym, "up": up})
    except:
        failed += 1
        continue
    time.sleep(random.uniform(0.5, 0.7))

result = {"board": "sz_main", "total": 50, "rising": rising, "failed": failed, "stocks": stocks_result}
print("FINAL_RESULT:")
print(json.dumps(result, ensure_ascii=False))
