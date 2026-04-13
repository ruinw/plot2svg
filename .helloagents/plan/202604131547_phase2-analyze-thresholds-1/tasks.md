# 任务清单: phase2-analyze-thresholds-1

```yaml
@feature: phase2-analyze-thresholds-1
@created: 2026-04-13
@status: completed
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 5/5 (100%) | 更新: 2026-04-13 15:54:00
当前: Phase 2 analyze 第一批阈值治理已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 5 | 0 | 0 | 5 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 在 `tests/test_config.py` 中补充 analyze 第一批阈值字段的失败测试 | depends_on: []
- [√] 1.2 在 `tests/test_analyze.py` 中补充自定义 route / signature 阈值的失败测试 | depends_on: []

### 2. 配置与实现

- [√] 2.1 扩展 `src/plot2svg/config.py` 中的 `ThresholdConfig`，新增 analyze 第一批阈值字段 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/analyze.py` 与 `src/plot2svg/pipeline.py`，让 analyze 读取配置 | depends_on: [1.2, 2.1]

### 3. 验证

- [√] 3.1 运行 config / analyze 相关测试，确认默认行为不变、可自定义阈值生效 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-13 15:47:00 | 方案包创建 | completed | 已建立 Phase 2 analyze 第一批阈值方案包 |
| 2026-04-13 15:49:00 | 1.1 / 1.2 | completed | 补充 analyze 阈值字段和自定义阈值失败测试，并确认当前缺口存在 |
| 2026-04-13 15:52:00 | 2.1 / 2.2 | completed | 扩展 `ThresholdConfig` 并让 analyze 与 pipeline 读取配置 |
| 2026-04-13 15:54:00 | 3.1 | completed | 在主工作区样本目录下验证 worktree 代码，config 与 analyze 相关测试通过 |

---

## 执行备注

- 本轮只处理 route selection 与 signature line-art detection 阈值。
- 这批改动继续严格按 TDD 推进，先验证配置接口尚未覆盖这组阈值。
