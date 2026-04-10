# 任务清单: phase2-graph-builder-thresholds-2

```yaml
@feature: phase2-graph-builder-thresholds-2
@created: 2026-04-10
@status: in_progress
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-10 19:03:00
当前: Phase 2 第二批 graph_builder 阈值治理已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 在 `tests/test_config.py` 中补充第二批 graph_builder 阈值字段的失败测试 | depends_on: []
- [√] 1.2 在 `tests/test_graph_builder.py` 中补充 near miss / partial edge 读取自定义阈值的失败测试 | depends_on: []

### 2. 配置与实现

- [√] 2.1 扩展 `src/plot2svg/config.py` 中的 `ThresholdConfig`，新增第二批 graph_builder 阈值字段 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/graph_builder.py`，让相关 helper 读取这组阈值 | depends_on: [1.2, 2.1]

### 3. 验证

- [√] 3.1 运行 config / graph_builder 相关测试，确认默认行为不变、可自定义阈值生效 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-10 18:48:00 | 方案包创建 | completed | 已建立 Phase 2 graph_builder 第二批阈值方案包 |
| 2026-04-10 18:52:00 | 1.1 / 1.2 | completed | 补充第二批阈值字段和自定义阈值失败测试，并确认当前缺口存在 |
| 2026-04-10 18:59:00 | 2.1 / 2.2 | completed | 扩展 `ThresholdConfig` 并让 graph_builder 的吸附/partial/text-cluster 过滤读取配置 |
| 2026-04-10 19:03:00 | 3.1 | completed | config 与 graph_builder 相关测试通过，默认行为与自定义阈值行为均已验证 |

---

## 执行备注

- 本轮继续 graph_builder 阈值治理，但只聚焦端点吸附 / partial edge / text cluster 过滤。
- 这批改动严格按 TDD 推进，先验证配置接口尚未覆盖这组阈值。
