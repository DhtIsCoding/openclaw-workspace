# Tushare 日线数据采集器

## 概述

全市场 A 股日线数据采集方案，基于 Tushare API (120积分限制)。

## 数据源

| 数据类型 | 来源 | 限制 |
|---------|------|------|
| 股票列表 | Sina API | 无限制 |
| 日线 OHLCV | Tushare daily | 50次/分钟, 8000次/天 |

## 文件结构

```
scripts/
  tushare_daily.py    # 主采集器
  query_daily.py      # 数据查询工具

data/
  tushare_daily.db    # SQLite 数据库
  tushare_daily.log   # 采集日志
```

## 数据库表结构

### stock_basic
| 字段 | 类型 | 说明 |
|------|------|------|
| ts_code | TEXT | 股票代码 (000001.SZ) |
| symbol | TEXT | 原始代码 |
| name | TEXT | 股票名称 |
| board | TEXT | 板块分类 |

### daily
| 字段 | 类型 | 说明 |
|------|------|------|
| ts_code | TEXT | 股票代码 |
| trade_date | TEXT | 交易日期 (YYYYMMDD) |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| vol | REAL | 成交量 |
| amount | REAL | 成交额 |

### fetch_progress
记录每只股票的最后更新日期，支持增量采集。

## 使用方法

### 增量采集（默认5天）
```bash
python3 scripts/tushare_daily.py
```

### 增量采集（指定天数）
```bash
python3 scripts/tushare_daily.py --days 10
```

### 强制更新股票列表
```bash
python3 scripts/tushare_daily.py --force-stocks
```

### 查看状态
```bash
python3 scripts/tushare_daily.py --status
```

### 数据查询
```bash
# 查询单只股票
python3 -c "
import sqlite3
conn = sqlite3.connect('data/tushare_daily.db')
c = conn.cursor()
rows = c.execute('''
    SELECT * FROM daily WHERE ts_code = ? ORDER BY trade_date DESC LIMIT 5
''', ('000001.SZ',)).fetchall()
for r in rows:
    print(r)
"

# 随机抽样
python3 -c "
import sqlite3
conn = sqlite3.connect('data/tushare_daily.db')
c = conn.cursor()
stocks = c.execute('SELECT DISTINCT ts_code FROM daily ORDER BY RANDOM() LIMIT 3').fetchall()
for s in stocks:
    print(s[0])
"
```

## 采集策略

### 频率控制
- 每分钟 40 次调用（留 10 次余量）
- 每次调用间隔 0.5-0.8 秒随机延时
- 遇到频率限制错误自动等待 65 秒后重试

### 批量请求
- 每批 50 只股票（符合 Tushare 限制）
- 5506 只股票 = 111 批次
- 完整采集约需 3 分钟

### 增量更新
- 记录每只股票的最后更新日期
- 每次只拉取新增日期的数据
- 支持中断后继续（断点续传）

### 每日调用量估算

| 场景 | 调用次数 | 状态 |
|------|---------|------|
| 全量采集 | ~111 次 | 完成 |
| 每日增量 | ~111 次 | 完成 |
| 每日剩余额度 | ~7890 次 | 可用于补充 |

## 当前数据状态

- 股票数量: 5506 只
- 历史记录: 21978 条 (4个交易日)
- 日均覆盖: 99.7%+

## 注意事项

1. **Token 管理**: token 存储在 `.tushare_token` 文件
2. **代理设置**: 脚本会自动清除代理环境变量（Tushare 直连）
3. **运行时间**: 建议在交易日 16:00 后运行
4. **数据完整性**: 当前 99.7% 覆盖，剩余 ~14 只股票可能停牌或无数据
