# 任务清单: phase2-thresholds-graph-builder

```yaml
@feature: phase2-thresholds-graph-builder
@created: 2026-04-09
@status: in_progress
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-09 17:26:00
当前: Phase 2 第一批阈值治理已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 在 `tests/test_config.py` 中补充 ThresholdConfig 相关失败测试 | depends_on: []
- [√] 1.2 在 `tests/test_graph_builder.py` 中补充 graph_builder 读取自定义阈值的失败测试 | depends_on: []

### 2. 配置与实现

- [√] 2.1 在 `src/plot2svg/config.py` 中新增 `ThresholdConfig`，并让 `PipelineConfig` 持有 profile 感知的默认阈值 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/graph_builder.py` 和 `src/plot2svg/pipeline.py`，接入第一批 monster stroke 阈值配置 | depends_on: [1.2, 2.1]

### 3. 验证

- [√] 3.1 运行 config / graph_builder 相关测试，确认默认行为不变、可自定义阈值生效 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-09 17:11:00 | 方案包创建 | completed | 已建立 Phase 2 第一批阈值治理方案包 |
| 2026-04-09 17:14:00 | 1.1 / 1.2 | completed | 补充 ThresholdConfig 和 graph_builder 自定义阈值失败测试，并确认当前缺口存在 |
| 2026-04-09 17:21:00 | 2.1 / 2.2 | completed | 新增 `ThresholdConfig`，并把 graph_builder 的 monster stroke 判定接入配置层 |
| 2026-04-09 17:26:00 | 3.1 | completed | config / graph_builder 相关测试通过，默认行为与自定义阈值行为均已验证 |

---

## 执行备注

- 本轮只接入 graph_builder 的第一批核心阈值，不扩散到其它模块。
- 这批改动严格按 TDD 推进，先验证配置骨架和 graph_builder 阈值接线目前都不存在。
