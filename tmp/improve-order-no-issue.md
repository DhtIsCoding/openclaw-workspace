## 📋 优化概述

**意图**：修复医嘱编号生成的高并发竞态条件，使用数据库序列替代 MAX()+1

**类型**：架构优化/可维护性

**来源**：Code Study - order 模块深度分析

## 🔍 问题描述

**现状**：
`infrastructure/persistence/order_repo_impl.go` 的 `NextOrderNo` 方法使用 `MAX(order_no)+1` 策略生成新编号，在高并发场景下可能产生编号冲突。

**影响**：
- 高并发时多条并发请求可能读到相同的 MAX 值，导致编号重复
- LIKE 前缀查询无法利用索引，数据量大时性能差
- 不同数据库字符串转数字实现不统一

## 💡 优化建议

### 方案描述
使用数据库序列替代 MAX()+1：
1. 创建序列 `order_no_seq`
2. `NextOrderNo` 改为 `SELECT NEXTVAL('order_no_seq')` 获取序号
3. 编号格式由应用层统一格式化

### 预期收益
- 消除并发竞态条件
- 查询性能提升
- 与 patient 模块的 NextPatientNo 保持一致

### 实现难度
- [ ] 低

## 📦 影响范围

| 范围 | 影响 |
|------|------|
| 服务 | order-service |

## ✅ 验收标准

- [ ] 单元测试覆盖并发场景
- [ ] uniqueIndex 约束作为最后保护

## 🔗 关联信息

| 关联 | 信息 |
|------|------|
| 源文档 | docs/research/code-studies/order-aggregate-state-machine-analysis.md |
