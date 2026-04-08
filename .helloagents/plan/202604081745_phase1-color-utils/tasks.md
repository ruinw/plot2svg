# 任务清单: phase1-color-utils

```yaml
@feature: phase1-color-utils
@created: 2026-04-08
@status: in_progress
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-08 18:05:00
当前: Phase 1 color_utils 批次已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 新增 `tests/test_color_utils.py`，先对 `plot2svg.color_utils` 的导入和关键颜色判断写出失败测试 | depends_on: []

### 2. 模块提取

- [√] 2.1 新建 `src/plot2svg/color_utils.py`，迁移颜色转换、颜色判断和 panel/arrow 采样函数 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/pipeline.py` 与 `src/plot2svg/object_svg_exporter.py`，改为从 `color_utils.py` 导入相关函数 | depends_on: [2.1]

### 3. 验证

- [√] 3.1 运行颜色工具测试和相关回归测试，确认行为保持不变 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-08 17:45:00 | 方案包创建 | completed | 已建立 Phase 1 color_utils 提取方案包 |
| 2026-04-08 17:50:00 | 1.1 | completed | 新增 `tests/test_color_utils.py`，并确认模块缺失时按预期失败 |
| 2026-04-08 18:00:00 | 2.1 / 2.2 | completed | 新建 `src/plot2svg/color_utils.py` 并回接 `pipeline.py` 与 `object_svg_exporter.py` |
| 2026-04-08 18:05:00 | 3.1 | completed | 颜色工具测试、export_svg 全套和相关 pipeline 回归均通过 |

---

## 执行备注

- 本轮聚焦颜色工具统一，不扩展到 bbox 工具模块化。
- 这批改动将严格按 TDD 推进，先验证新模块不存在时确实失败。
