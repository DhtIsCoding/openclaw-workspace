# Long-Term Memory

## 系统配置（持续更新）

- **Discord Bot**: 猫猫 (ID: 1478958720145817732)
- **Discord Server/Channel**: Momo / 1478967274193948763
- **Discord proxy**: `http://127.0.0.1:10808`（必须保留，dht在中国大陆）
- **GitHub**: DhtIsCoding 账户，PAT 在 `~/.github-token`
- **Gateway**: systemd service `openclaw-gateway.service`，端口 18789
- **WSL2 + Playwright**: `libasound2t64` 已安装，内置 Chromium 可运行

## EMR 评级项目（核心目标）

**目标：8级智慧医疗系统，通过评审**

当前评分进度（2026-04-08）：
| 领域 | 当前 | 目标 | 差距 |
|------|------|------|------|
| 病房医师 | 12 | 28 | 16 |
| 门诊医师 | 8 | 21 | 13 |
| 治疗信息处理 | 6 | 20 | 14 |
| 医疗保障 | 8 | 18 | 10 |
| 检查科室 | 0 | 14 | 14 |
| 护理管理 | 9 | 15 | 6 |
| 检验处理 (LIS) | 9 | 13 | 4 |
| CDR/文档 | 3 | 7 | 4 |
| **总计** | **55** | **170** | **115** |

## 关键架构决策

1. **Two-Phase Review**: fixed-reviewer 从 gh-issues 分离，处理合入后 PR 审查
2. **sub-agent 超时策略**: 默认 1 小时（3600秒），复杂任务 2 小时（7200秒）
3. **无 auto-merge**: 用户手动审查后才合并，只加 `fixed` label
4. **无多节点 dedup**: 单节点部署，无需重复执行保护
5. **Playwright 等待策略**: 金融行情页用 `domcontentloaded` + `waitForTimeout`，不用 `networkidle`（行情页用 WebSocket 实时推送）
6. **Discord 必须走代理**: `channels.discord.proxy` 配置不可删除

## 数据目录

- `~/.clawdbot/tasks/` - 任务队列、依赖、传入报告
- `~/.clawdbot/scoring/` - 评分引擎（评分规则、Issue映射、领域进度）
- `~/.clawdbot/dependency-graph/` - 服务依赖图
- `~/.clawdbot/memory/` - 系统记忆（错误模式、规则）
- `~/.clawdbot/goals/` - 目标跟踪器

## 经验教训（长期有效）

- ❌ `sessions_spawn` 后不要调用 `sessions_history` 轮询 → 会阻塞 completion push 机制
- ❌ 不要在 sub-agent spawn 后执行 `exec sleep` 轮询
- ✅ 东方财富等金融页面：WebSocket 长连接导致 `networkidle` 超时，改用 `domcontentloaded`
- ✅ MEMORY.md 保持在 12000 字节以下（OpenClaw 限制），定期精简
- ✅ Discord 代理配置在 `openclaw.json`，不在 systemd 环境变量
- ✅ Tushare stock_basic 每小时限制 1 次 → 用 Sina API 获取股票列表（无限制）
- ✅ Tushare daily 50次/分钟限制 → 每分钟 40 次留余量，错误时等待 65 秒

## 待办 / 在建

1. ~~scoring-engine~~ → 数据结构已完成
2. ~~dependency-scheduler~~ → 依赖图已完成
3. emr-researcher → 规划中
4. 30 个 GitHub Issues 待分配 milestone（Phase 1-4）
