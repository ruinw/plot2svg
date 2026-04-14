# 任务清单: phase4-ocr-layout-1

```yaml
@feature: phase4-ocr-layout-1
@created: 2026-04-14
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 3/3 (100%) | 更新: 2026-04-14 10:45:00
当前: Phase 4 OCR layout 已完成并通过相关测试
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 3 | 0 | 0 | 3 |

---

## 任务列表

### 1. 失败测试

- [√] 1.1 在 `tests/test_ocr.py` 中补充 overlay bbox 收紧和多行换行保留的失败测试 | depends_on: []
- [√] 1.2 在 `tests/test_export_svg.py` 中补充多行 `<tspan>` 导出的失败测试 | depends_on: []

### 2. 实现

- [√] 2.1 修改 `src/plot2svg/ocr.py` 与 `src/plot2svg/object_svg_exporter.py`，补齐 bbox 收紧和多行导出链路 | depends_on: [1.1, 1.2]

### 3. 验证

- [√] 3.1 运行相关测试，确认 bbox 更贴字、多行文本按行输出 | depends_on: [2.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-14 10:35:00 | 方案包创建 | completed | 已建立 Phase 4 OCR layout 方案包 |
| 2026-04-14 10:39:00 | 1.1 / 1.2 | completed | 补充 bbox 收紧、多行换行保留和 `<tspan>` 导出的失败测试 |
| 2026-04-14 10:43:00 | 2.1 | completed | 完成 OCR bbox 收紧、多行换行保留和 `<tspan>` 导出链路 |
| 2026-04-14 10:45:00 | 3.1 | completed | 相关聚焦测试和整份 `test_ocr.py` / `test_export_svg.py` 通过 |
