📚 **Code Study Report** | 2026-04-10

深度阅读了 2 个核心模块，以下是摘要：

---

**模块 1: patient / 患者聚合根**

核心设计：
- 六边形架构：domain 层零外部依赖，repository 接口在 domain 层定义，实现在 infrastructure 层
- 快照 + 事件双写：patients 快照表（快速加载）+ event_store（完整审计轨迹）
- PII 加密存储：证件号/电话加密 + hash 双重存储，符合医疗数据合规
- 状态机：active → merged/deceased，merged 状态有写保护

发现的问题：
- NextPatientNo 的实现路径不一致（达梦 vs 其他数据库）
- deceased 状态缺乏写保护
- 合并操作缺少幂等性保护

---

**模块 2: order / 医嘱服务**

核心设计：
- 三聚合根架构：MedicalOrder（住院）、LabOrder（检验）、ImagingOrder（影像）
- 整数状态机：0→1→2→3→4 / -1→-2，停嘱仅限 LDA，皮试阳性自动退回
- 跳跃式状态更新（ImagingOrder）：事件乱序时自动补全中间状态，防御性设计
- 参数对象模式：20+ 字段用 IssueMedicalOrderParams 结构体封装

发现的问题：
- 🔴 NextOrderNo 用 MAX()+1，高并发有编号冲突风险 → 已建 Issue #455
- CDSS 校验失败仅 WARN 日志，缺少明确开关和审计标记 → 已建 Issue #456
- ImagingOrder.MarkReported 自动补全时复用时间戳，影响审计准确性

---

📄 完整分析已写入：
- `docs/research/code-studies/patient-aggregate-root-analysis.md`
- `docs/research/code-studies/order-aggregate-state-machine-analysis.md`

🐙 Issues:
- #455 `[Improve] order - NextOrderNo 使用 MAX()+1 存在并发编号冲突风险`
- #456 `[Improve] order - CDSS 校验失败时应标记审计并支持配置降级策略`
