import urllib.request
import json
import time
import random

symbols_raw = ["sz300750","sz300015","sz300059","sz300122","sz300274","sz300760","sz300142","sz300223","sz300601","sz300059","sz300122","sz300274","sz300760","sz300015","sz300122","sz300274","sz300059","sz300750","sz300122","sz300760","sz300015","sz300059","sz300122","sz300274","sz300760","sz300059","sz300750","sz300122","sz300760","sz300015","sz300059","sz300122","sz300274","sz300760","sz300059","sz300122","sz300274","sz300015","sz300750","sz300122","sz300274","sz300760","sz300059","sz300122","sz300760","sz300015","sz300059","sz300122","sz300274","sz300760","sz300059"]

results = []
cache = {}
failed = 0

for sym in symbols_raw:
    if sym in cache:
        results.append({"symbol": sym, "up": cache[sym]["up"], "cached": True})
        delay = random.uniform(0.5, 0.7)
        time.sleep(delay)
        continue

    url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=5&datalen=11"
    
    retries = 0
    success = False
    up = False
    
    while retries < 2:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
            if isinstance(data, list) and len(data) >= 2:
                first_close = float(data[0]['close'])
                last_close = float(data[-1]['close'])
                up = last_close > first_close
                success = True
                cache[sym] = {"up": up}
            break
        except Exception as e:
            retries += 1
            if retries >= 2:
                failed += 1
            else:
                time.sleep(0.5)
    
    results.append({"symbol": sym, "up": up if success else None, "failed": not success})
    
    delay = random.uniform(0.5, 0.7)
    time.sleep(delay)

rising = sum(1 for r in results if r.get("up") == True)
total = len(results)
failed_count = failed

stocks_out = []
for r in results:
    if "failed" in r and r["failed"]:
        stocks_out.append({"symbol": r["symbol"], "up": None})
    else:
        stocks_out.append({"symbol": r["symbol"], "up": r["up"]})

output = {"board": "cyb", "total": total, "rising": rising, "failed": failed_count, "stocks": stocks_out}
print(json.dumps(output, ensure_ascii=False))
