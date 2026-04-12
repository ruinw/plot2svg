# 任务清单: phase2-ocr-thresholds-1

```yaml
@feature: phase2-ocr-thresholds-1
@created: 2026-04-12
@status: completed
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-12 09:02:00
当前: Phase 2 OCR 第一批阈值治理已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 在 `tests/test_config.py` 中补充 OCR 阈值字段的失败测试 | depends_on: []
- [√] 1.2 在 `tests/test_ocr.py` 中补充 early-exit / pixel-std 读取自定义阈值的失败测试 | depends_on: []

### 2. 配置与实现

- [√] 2.1 扩展 `src/plot2svg/config.py` 中的 `ThresholdConfig`，新增 OCR 第一批阈值字段 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/ocr.py`，让 early-exit / pixel-std 读取配置 | depends_on: [1.2, 2.1]

### 3. 验证

- [√] 3.1 运行 config / ocr 相关测试，确认默认行为不变、可自定义阈值生效 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-12 08:44:00 | 方案包创建 | completed | 已建立 Phase 2 OCR 第一批阈值方案包 |
| 2026-04-12 08:49:00 | 1.1 / 1.2 | completed | 补充 OCR 阈值字段和自定义阈值失败测试，并确认当前缺口存在 |
| 2026-04-12 08:56:00 | 2.1 / 2.2 | completed | 扩展 `ThresholdConfig` 并让 OCR 的 early-exit / pixel-std 读取配置 |
| 2026-04-12 09:02:00 | 3.1 | completed | config 与 OCR 相关测试通过，默认行为与自定义阈值行为均已验证 |

---

## 执行备注

- 本轮只处理 early-exit 和 pixel-std 两类阈值。
- 这批改动严格按 TDD 推进，并且已完成针对性验证。
