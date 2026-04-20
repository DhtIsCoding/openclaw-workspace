# space-stock-data

A股商业航天板块实时数据查询 Skill

## 功能

通过东方财富 + 新浪财经 API 采集实时数据，返回：
- 商业航天板块资金流入前十股票
- 个股实时价格
- 个股资金流向详情

## 使用方式

### 命令

- `查商业航天资金流入前十` / `今日商业航天板块资金流入`
- `查 [股票代码或名称] 实时价格`
- `查 [股票代码或名称] 资金流向`
- `商业航天板块完整报告`

### 调用方式

```bash
python3 /home/dht/.openclaw/workspace/scripts/space_stock_collector.py
```

输出文件：
- JSON 报告：`~/.openclaw/workspace/tmp/space_stock_report.json`
- 日志：`stdout/stderr`

## 数据源

- **资金流**：东方财富 `push2.eastmoney.com/api/qt/clist/get`（按主力净流入排序）
- **实时价格**：新浪财经 `hq.sinajs.cn`（每笔实时行情）

## 采集器路径

```
/home/dht/.openclaw/workspace/scripts/space_stock_collector.py
```

## 注意事项

- 数据采集依赖网络请求，每次调用约需 2-3 秒
- 东方财富接口在交易时间（9:30-15:00）实时更新
- 非交易时间数据为上一交易日收盘数据
- 资金流单位：元（展示时转换为亿元）
