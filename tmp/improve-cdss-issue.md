## 📋 优化概述

**意图**：CDSS 校验服务调用失败时，应使用更明确的降级策略并记录审计标记

**类型**：代码质量/安全性

**来源**：Code Study - order 模块深度分析

## 🔍 问题描述

**现状**：
`application/command/order_commands.go` 的 `validateWithCDSS` 方法在 CDSS 服务调用失败时，仅记录 WARN 日志后放行：

```go
if err != nil {
    log.Printf("[WARN] order cdss validate failed, continue degraded: %v", err)
    return nil  // CDSS 失败时继续放行
}
```

**影响**：
- 高风险药品校验被绕过，可能给患者带来安全风险
- 缺少明确的配置开关，团队难以判断当前是否启用了 CDSS 校验
- 事件中缺少 `cdssValidationBypassed` 标记，事后无法追溯哪些医嘱跳过了 CDSS 校验

## 💡 优化建议

### 方案描述
1. 增加明确的配置项 `cdss.enabled`（默认 true），非运行时判断
2. CDSS 调用失败时记录 ERROR 级别日志（而非 WARN）
3. 在 `MedicalOrderIssued` 事件中增加 `CDSSValidationBypassed bool` 字段，审计追溯

### 预期收益
- 安全性提升：可配置是否允许 CDSS 降级
- 可追溯性：事件中标记降级，事后可查
- 运维友好：ERROR 日志更容易被监控系统告警

### 实现难度
- [ ] 中

## 📦 影响范围

| 范围 | 影响 |
|------|------|
| 服务 | order-service |
| 事件 | MedicalOrderIssued payload 变更（需要事件版本升级）|

## ✅ 验收标准

- [ ] 配置项控制 CDSS 降级行为
- [ ] 失败时记录 ERROR 且事件含 bypassed 标记
- [ ] 单元测试覆盖 CDSS 失败场景

## 🔗 关联信息

| 关联 | 信息 |
|------|------|
| 源文档 | docs/research/code-studies/order-aggregate-state-machine-analysis.md |
