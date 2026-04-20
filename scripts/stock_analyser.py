"""
A股个股综合分析数据采集器 v2
整合：资金流 + 外资 + 机构持仓 + 新闻 + 公告 + 研报 + 行业链 + 实时价格
数据源：东方财富 + 新浪财经 + akshare
"""

import sys
import os

# ===== 最早清除所有代理变量 =====
for _k in list(os.environ.keys()):
    if "_proxy" in _k.lower():
        os.environ.pop(_k, None)
# ===============================

import json
import time
import logging
import subprocess
from datetime import datetime
from typing import Any
import shutil

import requests
import akshare as ak

sys.path.insert(0, '/home/dht/.openclaw/workspace')

sys.path.insert(0, '/home/dht/.openclaw/workspace')
from Ashare import get_price

# ===================== 配置 =====================
SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
EMONEY_HEADERS = {
    "Referer": "https://data.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

LOGGER = logging.getLogger("stock_analyser")


# ===================== 工具 =====================
def norm_code(code: str) -> tuple[str, str]:
    """标准化股票代码 → (纯数字code, 市场前缀sh/sz)"""
    c = code.strip().upper()
    if c.endswith(".SH") or c.startswith("SH"):
        num = c.replace("SH", "").replace(".", "")
        return num, "sh"
    elif c.endswith(".SZ") or c.startswith("SZ"):
        num = c.replace("SZ", "").replace(".", "")
        return num, "sz"
    elif c.startswith("6"):
        return c, "sh"
    elif c.startswith(("0", "3")):
        return c, "sz"
    else:
        return c, "sh"


def format_money(v: float) -> str:
    if abs(v) >= 1e8:
        return f"{v/1e8:.2f}亿"
    elif abs(v) >= 1e4:
        return f"{v/1e4:.2f}万"
    return f"{v:.2f}"


# ===================== 实时价格 =====================
class RealtimePrice:
    """新浪财经实时行情"""

    @staticmethod
    def get(codes: list[str]) -> dict[str, dict]:
        """
        codes: ["sh600879", "sz000001", ...]
        返回 {code: {name, price, change_pct, high, low, volume, ...}}
        """
        code_str = ",".join(codes)
        url = f"https://hq.sinajs.cn/list={code_str}"
        r = requests.get(url, headers=SINA_HEADERS, timeout=10)
        r.encoding = "gbk"

        results = {}
        for line in r.text.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("=")
            if len(parts) < 2:
                continue
            raw_code = parts[0].strip().replace("var hq_str_", "")
            data_str = parts[1].strip().strip('"')
            fields = data_str.split(",")
            if len(fields) < 10:
                continue

            price = float(fields[3])  # 当前价
            close = float(fields[2])  # 昨收
            change_pct = (price - close) / close * 100 if close else 0

            results[raw_code] = {
                "name": fields[0],
                "open": float(fields[1]) if fields[1] else 0,
                "close": close,
                "high": float(fields[4]) if fields[4] else 0,
                "low": float(fields[5]) if fields[5] else 0,
                "price": price,
                "volume": int(fields[8]) if fields[8] else 0,
                "amount": float(fields[9]) if fields[9] else 0,
                "change_pct": round(change_pct, 2),
                "update_date": fields[30] if len(fields) > 30 else "",
                "update_time": fields[31] if len(fields) > 31 else "",
            }
        return results


# ===================== 资金流向 =====================
class FundFlow:
    """资金流数据"""

    @staticmethod
    def history(stock: str, days: int = 20) -> list[dict]:
        """
        akshare 历史资金流（主力/超大单/大单/中单/小单）
        """
        code, mkt = norm_code(stock)
        mkt_map = {"sh": "sh", "sz": "sz"}
        try:
            df = ak.stock_individual_fund_flow(stock=code, market=mkt_map[mkt])
            records = []
            for _, row in df.head(days).iterrows():
                records.append({
                    "date": str(row.get("日期", "")),
                    "close": row.get("收盘价"),
                    "change_pct": row.get("涨跌幅"),
                    "main_inflow": row.get("主力净流入-净额"),
                    "main_ratio": row.get("主力净流入-净占比"),
                    "huge_inflow": row.get("超大单净流入-净额"),
                    "big_inflow": row.get("大单净流入-净额"),
                    "mid_inflow": row.get("中单净流入-净额"),
                    "small_inflow": row.get("小单净流入-净额"),
                })
            return records
        except Exception as e:
            LOGGER.warning(f"资金流历史失败 {stock}: {e}")
            return []

    @staticmethod
    def today(stock: str) -> dict:
        """
        东财资金流（今日 + 历史）- 使用 CDP 浏览器采集
        通过 MostLogin 浏览器（端口 50840）控制真实浏览器渲染页面
        优点：WAF 无法封禁（真实浏览器流量），返回完整字段
        """
        code, _ = norm_code(stock)
        try:
            import subprocess, os, json as _json
            cdp_script = "/home/dht/.openclaw/workspace/scripts/cdp_fund_flow.js"
            if not os.path.exists(cdp_script):
                return {}
            result = subprocess.run(
                ["node", cdp_script, code],
                capture_output=True, text=True, timeout=20
            )
            if result.returncode != 0:
                return {}
            data = _json.loads(result.stdout)
            rows = data.get("tableRows", [])
            # 找第一个有数据的行（跳过表头空行）
            today = next((r for r in rows if r.get('日期')), {})
            if not today:
                return {}
            # 解析金额字符串（6.36亿 → 636000000）
            def parse_money(s):
                if not s or s == '-':
                    return 0
                s = str(s).strip()
                mult = 1
                if '亿' in s:
                    mult, s = 1e8, s.replace('亿', '')
                elif '万' in s:
                    mult, s = 1e4, s.replace('万', '')
                try:
                    return float(s) * mult
                except:
                    return 0
            main = parse_money(today.get('主力净流入', '0'))
            huge = parse_money(today.get('超大单净流入', '0'))
            big = parse_money(today.get('大单净流入', '0'))
            mid = parse_money(today.get('中单净流入', '0'))
            small = parse_money(today.get('小单净流入', '0'))
            return {
                "price": float(today.get('收盘价', 0)),
                "change_pct": float(str(today.get('涨跌幅', '0')).replace('%', '')),
                "main_flow": main,
                "main_ratio": 0,
                "huge_flow": huge,
                "big_flow": big,
                "mid_flow": mid,
                "small_flow": small,
                "history": [
                    {"date": r.get('日期', ''), "main_inflow": parse_money(r.get('主力净流入', '0')),
                     "close": float(r.get('收盘价', 0)),
                     "change_pct": float(str(r.get('涨跌幅', '0')).replace('%', ''))}
                    for r in rows if r.get('日期')
                ],
            }
        except Exception as e:
            LOGGER.warning(f"今日资金流失败 {stock}: {e}")
            return {}


# ===================== 外资持股 =====================
class ForeignHolder:
    """外资（北向资金）持股数据"""

    @staticmethod
    def history(stock: str, days: int = 30) -> list[dict]:
        """
        akshare 北向资金历史持股
        """
        code, _ = norm_code(stock)
        try:
            df = ak.stock_hsgt_individual_em(symbol=code)
            records = []
            for _, row in df.head(days).iterrows():
                records.append({
                    "date": str(row.get("持股日期", "")),
                    "price": row.get("当日收盘价"),
                    "change_pct": row.get("当日涨跌幅"),
                    "hold_volume": row.get("持股数量"),
                    "hold_value": row.get("持股市值"),
                    "a_share_ratio": row.get("持股数量占A股百分比"),
                    "add_volume": row.get("今日增持股数"),
                    "add_value": row.get("今日增持资金"),
                    "value_change": row.get("今日持股市值变化"),
                })
            return records
        except Exception as e:
            LOGGER.warning(f"外资持股失败 {stock}: {e}")
            return []

    @staticmethod
    def latest(stock: str) -> dict:
        """最新外资持股"""
        records = ForeignHolder.history(stock, days=5)
        if records:
            return records[0]
        return {}


# ===================== 机构持仓 =====================
class InstitutionHolder:
    """机构（基金/QFII/社保）持仓"""

    @staticmethod
    def detail(stock: str, quarter: str = "20254") -> list[dict]:
        """
        akshare 机构持仓明细
        quarter: YYYYQ 如 20254 = 2025年Q4
        """
        code, _ = norm_code(stock)
        try:
            df = ak.stock_institute_hold_detail(stock=code, quarter=quarter)
            records = []
            for _, row in df.iterrows():
                records.append({
                    "type": row.get("持股机构类型"),
                    "code": row.get("持股机构代码"),
                    "name": row.get("持股机构简称"),
                    "hold_volume": row.get("持股数"),
                    "latest_volume": row.get("最新持股数"),
                    "ratio": row.get("持股比例"),
                    "latest_ratio": row.get("最新持股比例"),
                    "float_ratio": row.get("占流通股比例"),
                    "latest_float_ratio": row.get("最新占流通股比例"),
                    "ratio_change": row.get("持股比例增幅"),
                })
            return records
        except Exception as e:
            LOGGER.warning(f"机构持仓失败 {stock}: {e}")
            return []


# ===================== 新闻与公告 =====================
class StockNews:
    """个股新闻、公告、研报"""

    @staticmethod
    def news(stock: str, limit: int = 10) -> list[dict]:
        """
        akshare 个股新闻（包含利好/利空线索）
        """
        code, _ = norm_code(stock)
        try:
            df = ak.stock_news_em(symbol=code)
            records = []
            for _, row in df.head(limit).iterrows():
                content = str(row.get("新闻内容", ""))[:200]
                records.append({
                    "time": row.get("发布时间", ""),
                    "title": row.get("新闻标题", ""),
                    "content": content,
                    "source": row.get("文章来源", ""),
                    "url": row.get("新闻链接", ""),
                })
            return records
        except Exception as e:
            LOGGER.warning(f"新闻获取失败 {stock}: {e}")
            return []

    @staticmethod
    def announcements(stock: str) -> list[dict]:
        """
        东财个股公告
        """
        code, _ = norm_code(stock)
        url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
        params = {
            "sr": "-1",
            "page_size": 10,
            "page_index": 1,
            "ann_type": "SHA,CYB,GEM,SZA,NSE",
            "client_source": "web",
            "stock_list": code,
        }
        try:
            r = requests.get(url, params=params, headers=EMONEY_HEADERS, timeout=10)
            data = r.json()
            # 实际结构: data.data = {"list": [...], "total_hits": ...}
            items = data.get("data", {}).get("list", []) if isinstance(data.get("data"), dict) else data.get("data", [])
            records = []
            pos_kw = ["中标", "签约", "订单", "突破", "合作", "增长", "盈利", "获奖", "获批", "通过", "增持", "回购"]
            neg_kw = ["亏损", "处罚", "整改", "召回", "风险", "减持", "诉讼", "大跌", "暂停", "ST", "退市", "破产"]
            for item in items:
                if isinstance(item, dict):
                    title = item.get("title", "") or ""
                else:
                    title = str(item)
                sentiment = "中性"
                for kw in pos_kw:
                    if kw in title:
                        sentiment = "利好"
                        break
                for kw in neg_kw:
                    if kw in title:
                        sentiment = "利空"
                        break
                date = ""
                if isinstance(item, dict):
                    nd = item.get("notice_date", "") or item.get("art_time", "") or ""
                    date = str(nd)[:10]
                records.append({"date": date, "title": title, "sentiment": sentiment})
            return records
        except Exception as e:
            LOGGER.warning(f"公告获取失败 {stock}: {e}")
            return []

    @staticmethod
    def research_reports(stock: str, limit: int = 5) -> list[dict]:
        """
        akshare 券商研报
        """
        code, _ = norm_code(stock)
        try:
            df = ak.stock_research_report_em(symbol=code)
            records = []
            for _, row in df.head(limit).iterrows():
                records.append({
                    "date": row.get("日期", ""),
                    "title": row.get("报告名称", ""),
                    "rating": row.get("东财评级", ""),
                    "org": row.get("机构", ""),
                    "target_price": row.get("2026-盈利预测-收益", ""),  # 目标价
                    "pe_2026": row.get("2026-盈利预测-市盈率", ""),
                    "industry": row.get("行业", ""),
                    "pdf_url": row.get("报告PDF链接", ""),
                })
            return records
        except Exception as e:
            LOGGER.warning(f"研报获取失败 {stock}: {e}")
            return []


# ===================== 产业逻辑链 =====================
class IndustryChain:
    """产业链关系"""

    @staticmethod
    def board_stocks(board_name: str) -> list[dict]:
        """
        获取某行业板块成分股
        """
        try:
            df = ak.stock_board_industry_cons_em(symbol=board_name)
            records = []
            for _, row in df.iterrows():
                records.append({
                    "code": str(row.get("代码", "")),
                    "name": row.get("名称", ""),
                    # 其他字段取决于具体板块数据
                })
            return records
        except Exception as e:
            LOGGER.warning(f"板块成分股失败 {board_name}: {e}")
            return []

    @staticmethod
    def related_boards(stock: str) -> list[str]:
        """
        根据主营构成推断关联行业板块
        """
        code, _ = norm_code(stock)
        # 商业航天相关板块关键词
        boards = [
            "商业航天", "航天航空", "卫星导航", "军工",
            "通信设备", "电子信息", "国防军工", "航天装备",
        ]
        return boards


# ===================== 财务数据 =====================
class Financials:
    """财务数据"""

    @staticmethod
    def basic_info(stock: str) -> dict:
        """
        个股基本信息
        注意：akshare 的 stock_individual_info_em 内部走 push2.eastmoney.com，
        在代理环境下可能失败，已加容错。
        """
        code, _ = norm_code(stock)
        try:
            df = ak.stock_individual_info_em(symbol=code)
            info = {}
            for _, row in df.iterrows():
                info[row.get("item", "")] = row.get("value", "")
            return info
        except Exception as e:
            LOGGER.warning(f"基本信息失败 {stock}: {e}")
            # 降级：用股票代码表获取基本信息
            try:
                names = ak.stock_info_a_code_name()
                row = names[names["code"] == code]
                if not row.empty:
                    return {"name": row.iloc[0]["name"], "code": code, "note": "limited (push2 blocked)"}
            except Exception:
                pass
            return {"note": "基本信息暂不可用"}


# ===================== 综合报告生成器 =====================
class StockAnalyser:
    """
    个股综合分析报告
    一次性整合：价格 + 资金流 + 外资 + 机构 + 新闻 + 公告 + 研报 + 产业
    """

    def __init__(self, stock: str):
        self.stock = stock
        self.code, self.mkt = norm_code(stock)
        self._price_cache = {}

    def _get_price(self) -> dict:
        """获取实时价格（带缓存）"""
        if not self._price_cache:
            prefix = "sh" if self.mkt == "sh" else "sz"
            result = RealtimePrice.get([f"{prefix}{self.code}"])
            self._price_cache = result.get(f"{prefix}{self.code}", {})
        return self._price_cache

    def analyse(self) -> dict:
        """
        生成完整分析报告
        """
        price = self._get_price()
        name = price.get("name", self.code)

        return {
            "stock": self.stock,
            "name": name,
            "code": self.code,
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

            # 实时行情
            "realtime": {
                "price": price.get("price"),
                "open": price.get("open"),
                "close": price.get("close"),
                "high": price.get("high"),
                "low": price.get("low"),
                "change_pct": price.get("change_pct"),
                "volume": price.get("volume"),
                "amount": price.get("amount"),
                "update_time": f"{price.get('update_date', '')} {price.get('update_time', '')}",
            },

            # 今日资金流
            "fund_flow_today": FundFlow.today(self.stock),

            # 近期资金流
            "fund_flow_history": FundFlow.history(self.stock, days=10),

            # 外资持股（北向）
            "foreign_holding": {
                "latest": ForeignHolder.latest(self.stock),
                "history": ForeignHolder.history(self.stock, days=30),
            },

            # 机构持仓
            "institution_holding": InstitutionHolder.detail(self.stock, quarter="20254"),

            # 新闻
            "news": StockNews.news(self.stock, limit=10),

            # 公告
            "announcements": StockNews.announcements(self.stock),

            # 研报
            "research_reports": StockNews.research_reports(self.stock, limit=5),

            # 基本信息
            "basic_info": Financials.basic_info(self.stock),
        }

    def summary(self) -> dict:
        """
        精简摘要（用于快速回复）
        """
        analysis = self.analyse()
        price = analysis["realtime"]
        ff = analysis["fund_flow_today"]
        fh = analysis["fund_flow_history"]
        fh_records = analysis["fund_flow_history"]
        foreign = analysis["foreign_holding"]
        fl = foreign.get("latest", {})
        anns = analysis["announcements"]
        news = analysis["news"]
        reports = analysis["research_reports"]

        # 近5日主力净流入合计
        main_inflow_5d = sum(r.get("main_inflow", 0) or 0 for r in fh_records[:5])

        # 公告情绪统计
        pos_cnt = sum(1 for a in anns if a.get("sentiment") == "利好")
        neg_cnt = sum(1 for a in anns if a.get("sentiment") == "利空")

        return {
            "stock": f"{analysis['name']}({analysis['code']})",
            "price": price.get("price"),
            "change_pct": price.get("change_pct"),
            "today_main_flow": format_money(ff.get("main_flow", 0)),
            "main_flow_5d": format_money(main_inflow_5d),
            "foreign_ratio": fl.get("a_share_ratio"),
            "foreign_add": format_money(fl.get("add_value", 0) or 0),
            "pos_ann": pos_cnt,
            "neg_ann": neg_cnt,
            "news_count": len(news),
            "report_count": len(reports),
            "latest_report": reports[0] if reports else None,
            "report_time": analysis["report_time"],
        }


# ===================== CLI =====================
def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="A股个股综合分析")
    parser.add_argument("stock", help="股票代码，如 600879 或 sh600879")
    parser.add_argument("--full", action="store_true", help="输出完整JSON报告")
    parser.add_argument("--output", help="保存到文件")
    args = parser.parse_args()

    analyser = StockAnalyser(args.stock)

    if args.full:
        report = analyser.analyse()
    else:
        report = analyser.summary()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"已保存: {args.output}")

    # 打印
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
