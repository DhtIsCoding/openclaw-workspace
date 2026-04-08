# USER.md - About Your Human

- **Name:** dht
- **What to call them:** dht
- **Pronouns:** _(未知)_
- **Timezone:** Asia/Shanghai (GMT+8)
- **Notes:** 不喜欢被过度打扰，偏好安静高效的工作方式

## Context

- **主要工作：** 开发智慧医疗系统，目标是符合 **8级** 评级标准并通过评审，涵盖：
  - **HIS** — 医院信息系统
  - **CDR** — 临床数据仓库 / 文档注册中心
  - **IDSS** — 智能决策支持系统

- **技术栈（从日志推断）：**
  - Golang（XDS 相关实现：Folder、DocumentEntry、SubmissionSet 模型）
  - FHIR 标准（XDS ITI 规范）
  - RocketMQ（事件发布）
  - 微服务架构（多服务协同）

- **团队协作：**
  - 通过 GitHub 管理代码（多个 PR 并行推进）
  - 通过 Discord 接收自动化任务状态通知
  - 使用 OpenClaw 多 agent 系统做工作流自动化（orchestrator、fixed-reviewer 等）

- **个人风格/偏好：**
  - 希望 AI **仔细认真**，不冲动执行
  - 收到任务时：**先阅读相关上下文** → 遇到新知识先查官方文档/社区讨论 → 形成最佳结论 → 再执行
  - 不喜欢未经思考的快速回复，也不喜欢被过度打扰

## 项目关键路径（从日志提取）

| 域名 | 当前评分 | 目标 | 差距 |
|------|---------|------|------|
| 病房医师 | 12 | 28 | 16 |
| 门诊医师 | 8 | 21 | 13 |
| 治疗信息处理 | 6 | 20 | 14 |
| 医疗保障 | 8 | 18 | 10 |
| 检查科室 | 0 | 14 | 14 |
| 护理管理 | 9 | 15 | 6 |
| 检验处理 (LIS) | 9 | 13 | 4 |
| CDR/文档 | 3 | 7 | 4 |
| **总计** | **55** | **170** | **115** |

---

_This file is updated as I learn more about dht. Last updated: 2026-04-08._
