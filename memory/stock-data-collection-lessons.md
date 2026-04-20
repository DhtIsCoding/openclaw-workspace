# 数据采集经验总结（2026-04-20）

## 踩坑记录

### push2.eastmoney.com WAF 封禁事件

**经过**：
- 排查个股资金流数据时，对 push2.eastmoney.com 发起高频调试请求
- 30分钟内数十次无间隔请求，User-Agent 固定为 curl/8.5.0
- 代理环境下 Python requests 被关闭连接（TLS 指纹问题）
- 移除代理后 curl 直连也返回 Empty reply（IP 被 WAF 封禁）

**根本原因**：
1. 无请求间隔，高频打同一接口 → 触发 WAF 频率限制
2. 固定 curl UA，非真实浏览器指纹 → 被识别为爬虫
3. 有代理时 WAF 看到代理 IP，移除代理后真实 IP 暴露 → 封禁生效

**教训**：
- 发现返回字段不完整（f62/f184）= 服务端已识别可疑客户端，立即停手
- 调试必须控制频率（间隔 1-3 秒），不要连打
- 字段屏蔽是封禁的前兆，不是"能用就行"

---

## 数据采集最佳实践

### 1. 请求头最小集（东方财富必带）
```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Referer: https://data.eastmoney.com/   ← 东财所有接口必带
```

### 2. 请求间隔（强制）
```python
import time, random
time.sleep(random.uniform(1.0, 3.0))  # 每次请求前随机间隔
```

### 3. 字段屏蔽 = 停止请求信号
- 正常响应：返回完整字段（如 20+ 字段）
- 屏蔽响应：只返回 1-2 个字段（f62/f184）
- 出现屏蔽 → 立即停止请求，等 30 分钟再试

### 4. 验证 IP 干净度（采集前必做）
```bash
curl --max-time 5 "https://目标域名" || echo "IP可能被封"
```

### 5. 高频采集必须用代理池
- 单 IP 直打东财最多撑几分钟
- 需要：代理池 + 每次请求换 IP + 间隔 3-5 秒

### 6. 调试环境与生产分离
- 调试用 curl 直接测（能看到完整 TLS 过程）
- 确认通后再用 Python
- 不要在调试阶段高频打生产接口

---

## 东财数据接口可用性（2026-04-20 实测）

| 接口 | 域名 | 可用性 | 备注 |
|------|------|--------|------|
| 实时价格 | hq.sinajs.cn | ✅ | 新浪财经，免费 |
| 个股资金流历史 | akshare | ✅ | 内部走 push2（代理环境受限）|
| 外资持股 | akshare stock_hsgt_individual_em | ✅ | 北向资金历史 |
| 个股新闻 | akshare stock_news_em | ✅ | 证券时报等来源 |
| 个股公告 | np-anotice-stock.eastmoney.com | ✅ | 公告列表 |
| 研报 | akshare stock_research_report_em | ✅ | 含评级/目标价 |
| 机构持仓 | akshare stock_institute_hold_detail | ✅ | 基金/QFII/社保 |
| 板块资金流排名 | push2.eastmoney.com clist | ✅ | 按主力净流入排序 |
| push2 个股实时资金流 | push2.eastmoney.com stock/get | ❌ | WAF 封禁中 |
| 基本信息 | akshare stock_individual_info_em | ⚠️ | 内部走 push2，限流 |
| 今日主力净流入（单股）| datacenter-web.eastmoney.com | ⚠️ | 字段不完整 |

---

## CDP 浏览器方案（MostLogin）

### 已验证可用
- CDP 端口：50840（MostLogin 浏览器自动化平台）
- 控制方式：WebSocket + CDP 协议
- Node.js ws 库路径：`openclaw/node_modules/ws`
- 可控制真实浏览器访问任意页面，WAF 无法封禁

### 用途
- 替代被封的 push2 API
- 获取需要 JS 渲染的动态数据
- 更高质量的数据（完整字段，非屏蔽版）

### 待验证
- [ ] CDP 能否稳定导航到东财个股页面并提取数据
- [ ] 数据质量是否优于现有 akshare 接口
- [ ] 请求频率是否可控

### CDP 使用示例（Node.js）
```javascript
const WebSocket = require('/path/to/ws');
const ws = new WebSocket('ws://127.0.0.1:50840/devtools/page/PAGE_ID');
ws.send(JSON.stringify({id:1,method:'Page.enable'}));
ws.send(JSON.stringify({id:2,method:'Runtime.enable'}));
// 监听消息
ws.on('message', data => { ... });
// 执行 JS
ws.send(JSON.stringify({id:10,method:'Runtime.evaluate',params:{expression:'document.title'}}));
```

---

## 当前系统数据覆盖

- 实时价格 ✅
- 资金流历史（10日）✅
- 外资持股（30日）✅
- 最新研报（5条）✅
- 个股新闻（10条）✅
- 个股公告（10条）✅
- 机构持仓 ✅
- 板块资金流排名 ✅

缺失：
- push2 今日主力净流入（单股级别）→ 可通过板块接口补偿
- 基本信息（公司概况）→ 降级用股票代码表
