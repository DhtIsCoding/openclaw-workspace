"""
A股商业航天板块实时数据采集服务
数据源：东方财富 + 新浪财经
输出：标准 JSON，支持 HTTP Webhook 推送至 OpenClaw
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

import aiohttp
import requests

# ===================== 配置 =====================
EMONEY_HEADERS = {
    "Referer": "https://data.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

LOGGER = logging.getLogger("stock_collector")


# ===================== 工具函数 =====================
def format_money(v: float) -> str:
    """格式化资金数字"""
    if abs(v) >= 1e8:
        return f"{v/1e8:.2f}亿"
    elif abs(v) >= 1e4:
        return f"{v/1e4:.2f}万"
    return f"{v:.2f}"


def safe_get(d: dict, *keys, default: Any = None) -> Any:
    """安全获取嵌套字典"""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


# ===================== 东方财富 API =====================
class EastMoneyAPI:
    """东方财富数据接口"""

    @staticmethod
    def get_board_fund_flow(board_code: str = "BK0963", top_n: int = 20) -> dict:
        """
        获取板块资金流入排名
        board_code: BK0963=商业航天, BK0480=航天航空
        返回: {"板块名": [...个股资金流列表]}
        """
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": top_n,
            "po": 1,        # 按净流入降序
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f62",   # 按主力净流入排序
            "fs": f"b:{board_code}+f:!50",  # 板块内个股
            "fields": "f2,f3,f4,f12,f14,f62,f184",
        }
        r = requests.get(url, params=params, headers=EMONEY_HEADERS, timeout=10)
        data = r.json()

        records = []
        for item in data.get("data", {}).get("diff", []):
            records.append({
                "code": item.get("f12"),
                "name": item.get("f14"),
                "price": item.get("f2"),
                "change_pct": item.get("f3"),       # 涨跌幅%
                "change_dir": item.get("f4"),        # 涨跌额
                "fund_flow": item.get("f62", 0),     # 主力净流入(元)
                "fund_ratio": item.get("f184", 0),  # 主力净流入占比%
            })

        return {
            "board": board_code,
            "timestamp": datetime.now().isoformat(),
            "records": records
        }

    @staticmethod
    def get_stock_fund_flow(stock_code: str) -> dict:
        """
        获取单只个股资金流明细
        stock_code: 如 "600879.SH"
        """
        # 分离市场后缀
        if stock_code.endswith(".SH"):
            mkt = "1"  # 上交所
            code = stock_code.replace(".SH", "")
        else:
            mkt = "0"  # 深交所
            code = stock_code.replace(".SZ", "")

        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fltt": 2,
            "invt": 2,
            "wbp2u": "|0|0|0|web",
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124",
            "secid": f"{mkt}.{code}",
        }
        r = requests.get(url, params=params, headers=EMONEY_HEADERS, timeout=10)
        item = r.json().get("data", {})

        if not item:
            return {"error": f"No data for {stock_code}"}

        return {
            "code": item.get("f12"),
            "name": item.get("f14"),
            "price": item.get("f2"),
            "change_pct": item.get("f3"),
            "main_flow": item.get("f62", 0),        # 主力净流入
            "main_ratio": item.get("f184", 0),     # 主力净流入占比
            "huge_flow": item.get("f66", 0),       # 超大单净流入
            "huge_ratio": item.get("f69", 0),
            "big_flow": item.get("f72", 0),       # 大单净流入
            "big_ratio": item.get("f75", 0),
            "mid_flow": item.get("f78", 0),       # 中单净流入
            "mid_ratio": item.get("f81", 0),
            "small_flow": item.get("f84", 0),     # 小单净流入
            "small_ratio": item.get("f87", 0),
            "timestamp": datetime.now().isoformat(),
        }


# ===================== 新浪财经 API =====================
class SinaAPI:
    """新浪财经实时行情"""

    @staticmethod
    def get_realtime_prices(codes: list[str]) -> dict[str, dict]:
        """
        获取实时价格
        codes: ["sh600879", "sz000001", "sh601698"]
        """
        code_str = ",".join(codes)
        url = f"https://hq.sinajs.cn/list={code_str}"
        r = requests.get(url, headers=SINA_HEADERS, timeout=10)
        r.encoding = "gbk"

        results = {}
        for line in r.text.strip().split("\n"):
            if not line.strip():
                continue
            # var hq_str_sh600879="航天电子,23.490,23.420,25.440,25.660,23.490,25.440,25.450,...
            parts = line.split("=")
            if len(parts) < 2:
                continue
            code_part = parts[0].strip()  # var hq_str_sh600879
            code = code_part.replace("var hq_str_", "")
            data_str = parts[1].strip().strip('"')
            fields = data_str.split(",")
            if len(fields) < 10:
                continue

            name = fields[0]
            open_p = fields[1]
            close_p = fields[2]   # 昨收
            high = fields[3]
            low = fields[4]
            price = fields[5]     # 当前价
            vol = fields[8]       # 成交量(手)
            amount = fields[9]    # 成交额(元)
            update_time = fields[30] if len(fields) > 30 else ""
            update_date = fields[31] if len(fields) > 31 else ""

            results[code] = {
                "name": name,
                "open": float(open_p) if open_p else 0,
                "close": float(close_p) if close_p else 0,
                "high": float(high) if high else 0,
                "low": float(low) if low else 0,
                "price": float(price) if price else 0,
                "volume": int(vol) if vol else 0,
                "amount": float(amount) if amount else 0,
                "update_date": update_date,
                "update_time": update_time,
            }

        return results


# ===================== 东方财富 WebSocket (可选) =====================
class EastMoneyWebSocket:
    """
    东财 WebSocket 实时行情推送（进阶）
    用于替代轮询，降低延迟
    """

    def __init__(self):
        self.ws_url = "wss://push2.eastmoney.com/websocket"
        self.ws = None
        self.subscriptions = set()

    async def connect(self):
        import websockets
        self.ws = await websockets.connect(self.ws_url)
        LOGGER.info("WebSocket connected")

    async def subscribe(self, codes: list[str]):
        """订阅实时行情"""
        msg = {
            "type": "sub",
            "codes": codes,
            "dataType": "pushdetail",
        }
        await self.ws.send(json.dumps(msg))

    async def listen(self, callback):
        """监听数据推送"""
        async for msg in self.ws:
            data = json.loads(msg)
            await callback(data)


# ===================== 商业航天数据采集器 =====================
class SpaceStockCollector:
    """
    商业航天板块数据采集器
    采集：板块资金流、个股价格、个股资金流
    """

    # 商业航天相关个股初始列表（可根据板块动态更新）
    DEFAULT_STOCKS = [
        "sh600879",  # 航天电子
        "sh600372",  # 中航机载
        "sh600050",  # 中国联通
        "sh601698",  # 中国卫通
        "sz000901",  # 航天科技
        "sz300065",  # 海兰信
        "sz002565",  # 顺灏股份
        "sz300102",  # 乾照光电
        "sz002366",  # 融发核电
        "sz000063",  # 中兴通讯
        "sz002025",  # 航天电器
        "sz300136",  # 信维通信
        "sh600343",  # 航天动力
        "sz300699",  # 光威复材
        "sh600118",  # 中国卫星
        "sh601728",  # 中国电信
        "sz002149",  # 西部材料
        "sh603260",  # 航天宏图
    ]

    def __init__(self):
        self.em = EastMoneyAPI()
        self.sina = SinaAPI()
        self.stocks = self.DEFAULT_STOCKS.copy()

    def get_board_money_flow(self, top_n: int = 20) -> dict:
        """获取商业航天板块资金流入前十"""
        return self.em.get_board_fund_flow("BK0963", top_n)

    def get_stocks_price(self, codes: list[str] | None = None) -> dict:
        """获取个股实时价格"""
        codes = codes or self.stocks
        return self.sina.get_realtime_prices(codes)

    def get_stock_money_flow(self, stock_code: str) -> dict:
        """获取单只个股资金流"""
        return self.em.get_stock_fund_flow(stock_code)

    def get_full_report(self) -> dict:
        """
        生成完整商业航天数据报告
        包含：板块资金流 + 个股价格 + 今日净流入前十
        """
        # 1. 板块资金流
        board_data = self.em.get_board_fund_flow("BK0963", 30)

        # 2. 个股实时价格
        stock_codes = [f"sh{r['code']}" if r['code'].startswith('6') else f"sz{r['code']}"
                       for r in board_data.get("records", [])[:20]]
        if stock_codes:
            prices = self.sina.get_realtime_prices(stock_codes)
        else:
            prices = {}

        # 3. 合并数据
        records = []
        for item in board_data.get("records", []):
            code = item["code"]
            prefix = "sh" if code.startswith("6") else "sz"
            price_info = prices.get(f"{prefix}{code}", {})

            records.append({
                "rank": len(records) + 1,
                "code": code,
                "name": item["name"],
                "price": price_info.get("price", item.get("price")),
                "change_pct": item["change_pct"],
                "fund_flow_yi": round(item["fund_flow"] / 1e8, 2),  # 转为亿元
                "fund_ratio": item["fund_ratio"],
            })

        return {
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "board": "商业航天(BK0963)",
            "summary": {
                "total_stocks": len(records),
                "inflow_stocks": len([r for r in records if r["fund_flow_yi"] > 0]),
                "top10_inflow_sum": round(sum(r["fund_flow_yi"] for r in records[:10]), 2),
            },
            "top10_by_inflow": records[:10],
            "all_records": records,
        }


# ===================== HTTP Server (推送 OpenClaw) =====================
async def start_http_server(collector: SpaceStockCollector, port: int = 8765):
    """
    启动轻量 HTTP 服务器
    GET /report  → 返回完整报告(JSON)
    GET /health  → 健康检查
    """
    from aiohttp import web

    async def handle_report(request):
        try:
            report = collector.get_full_report()
            return web.json_response(report)
        except Exception as e:
            LOGGER.error(f"report error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_health(request):
        return web.json_response({"status": "ok", "time": datetime.now().isoformat()})

    app = web.Application()
    app.router.add_get("/report", handle_report)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", port)
    await site.start()
    LOGGER.info(f"HTTP server started on http://localhost:{port}")
    return site


# ===================== 主函数 =====================
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    collector = SpaceStockCollector()

    print("=" * 60)
    print("A股商业航天板块实时数据采集器")
    print("=" * 60)

    # 测试采集
    print("\n[1] 获取板块资金流数据...")
    report = collector.get_full_report()
    print(f"    报告时间: {report['report_time']}")
    print(f"    板块: {report['board']}")
    print(f"    统计: {report['summary']}")

    print("\n[2] 今日资金流入前十股票:")
    print(f"    {'排名':<4} {'代码':<10} {'名称':<10} {'价格':>8} {'涨幅%':>7} {'净流入(亿)':>12}")
    print("    " + "-" * 60)
    for s in report["top10_by_inflow"]:
        print(f"    {s['rank']:<4} {s['code']:<10} {s['name']:<10} "
              f"{s['price']:>8.2f} {s['change_pct']:>7.2f} {s['fund_flow_yi']:>12.2f}")

    # 保存报告
    report_path = "/home/dht/.openclaw/workspace/tmp/space_stock_report.json"
    import os
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {report_path}")

    # 启动 HTTP 服务（供 OpenClaw 定时调用）
    if "--server" in __import__("sys").argv:
        asyncio.run(start_http_server(collector))


if __name__ == "__main__":
    main()
