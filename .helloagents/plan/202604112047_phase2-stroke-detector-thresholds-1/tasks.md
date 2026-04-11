# 任务清单: phase2-stroke-detector-thresholds-1

```yaml
@feature: phase2-stroke-detector-thresholds-1
@created: 2026-04-11
@status: in_progress
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-11 21:02:00
当前: Phase 2 stroke_detector 第一批阈值治理已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 在 `tests/test_config.py` 中补充 stroke_detector 第一批阈值字段的失败测试 | depends_on: []
- [√] 1.2 在 `tests/test_stroke_detector.py` 中补充 sane / min length / dense reconstruction 读取自定义阈值的失败测试 | depends_on: []

### 2. 配置与实现

- [√] 2.1 扩展 `src/plot2svg/config.py` 中的 `ThresholdConfig`，新增 stroke_detector 第一批阈值字段 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/stroke_detector.py` 与 `src/plot2svg/pipeline.py`，让这组三类逻辑读取配置 | depends_on: [1.2, 2.1]

### 3. 验证

- [√] 3.1 运行 config / stroke_detector 相关测试，确认默认行为不变、可自定义阈值生效 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-11 20:47:00 | 方案包创建 | completed | 已建立 Phase 2 stroke_detector 第一批阈值方案包 |
| 2026-04-11 20:52:00 | 1.1 / 1.2 | completed | 补充 stroke_detector 阈值字段和自定义阈值失败测试，并确认当前缺口存在 |
| 2026-04-11 20:58:00 | 2.1 / 2.2 | completed | 扩展 `ThresholdConfig` 并让 stroke_detector 的 sanity / min length / dense reconstruction 读取配置 |
| 2026-04-11 21:02:00 | 3.1 | completed | config 与 stroke_detector 相关测试通过，默认行为与自定义阈值行为均已验证 |

---

## 执行备注

- 本轮只处理全局 sanity / 最小长度 / dense reconstruction 触发阈值。
- 这批改动严格按 TDD 推进，先验证配置接口尚未覆盖这组阈值。
