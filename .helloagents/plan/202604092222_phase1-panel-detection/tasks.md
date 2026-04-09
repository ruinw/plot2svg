# 任务清单: phase1-panel-detection

```yaml
@feature: phase1-panel-detection
@created: 2026-04-09
@status: in_progress
@mode: R2
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 4/4 (100%) | 更新: 2026-04-09 22:30:00
当前: Phase 1 panel_detection 批次已完成并通过针对性验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 4 | 0 | 0 | 4 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 新增 `tests/test_panel_detection.py`，先对 `plot2svg.panel_detection` 的导入和关键 panel 行为写出失败测试 | depends_on: []

### 2. 模块提取

- [√] 2.1 新建 `src/plot2svg/panel_detection.py`，迁移 panel 检测主函数和专属 helper | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/pipeline.py`，改为从 `panel_detection.py` 导入相关函数 | depends_on: [2.1]

### 3. 验证

- [√] 3.1 运行 panel_detection 测试和相关 pipeline / export_svg 回归测试，确认行为保持不变 | depends_on: [2.2]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-09 22:22:00 | 方案包创建 | completed | 已建立 Phase 1 panel_detection 提取方案包 |
| 2026-04-09 22:25:00 | 1.1 | completed | 新增 `tests/test_panel_detection.py`，并确认模块缺失时按预期失败 |
| 2026-04-09 22:28:00 | 2.1 / 2.2 | completed | 新建 `src/plot2svg/panel_detection.py` 并回接 `pipeline.py` |
| 2026-04-09 22:30:00 | 3.1 | completed | panel_detection 测试、相关 pipeline 回归和 panel_arrow 导出测试均通过 |

---

## 执行备注

- 本轮聚焦 panel 检测闭环，不扩展到非 panel 专属逻辑。
- 这批改动严格按 TDD 推进，先验证新模块不存在时确实失败。
