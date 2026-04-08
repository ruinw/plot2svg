> **@status:** completed | 2026-03-15 03:48

﻿# 任务清单: run-end-to-end-flowchart

```yaml
@feature: run-end-to-end-flowchart
@created: 2026-03-15
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 3/3 (100%) | 更新: 2026-03-15 03:50:00
当前: 已完成基线修复、回归验证和真实样本输出
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 3 | 0 | 0 | 3 |

---

## 任务列表

### 1. 运行准备

- [√] 1.1 确认 `picture/end_to_end_flowchart.png`、CLI 入口和关键依赖均可用 | depends_on: []

### 2. 基线执行

- [√] 2.1 运行 `python -X utf8 -m plot2svg.cli --input picture/end_to_end_flowchart.png --output outputs/end_to_end_flowchart --profile balanced --enhancement-mode auto` | depends_on: [1.1]

### 3. 结果检查

- [√] 3.1 检查 `final.svg` 是否生成，并汇总本次输出质量问题 | depends_on: [2.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-15 03:07:00 | package | completed | 已创建并填充方案包，等待执行 |
| 2026-03-15 03:08:00 | 1.1 | completed | 输入图片、CLI 入口和关键依赖检查通过 |
| 2026-03-15 03:36:00 | 2.1 | failed | 两次运行分别在 240s 和 900s 超时，未生成 `scene_graph.json` / `final.svg` |
| 2026-03-15 03:42:00 | debug | completed | 已定位根因为 oversized stroke mask 触发 dense reconstruction，`_estimate_hub(...)` 在大规模线段上退化过慢 |
| 2026-03-15 03:45:00 | fix | completed | 为 `stroke_detector._should_reconstruct_dense_lines(...)` 增加超大 mask 保护，真实样本基线重新跑通 |
| 2026-03-15 03:50:00 | 3.1 | completed | 已生成 `scene_graph.json` / `final.svg` 并完成回归验证 |

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等

- 用户在执行中选择继续诊断，因此本次任务从“只运行现有管线”扩展为“修复阻塞后再完成基线输出”。
- 根因证据：`stage2` 仅有 1 个 `stroke` 节点，但 bbox 为 `[12, 14, 1396, 757]`，几乎覆盖整张图；其 mask 非零像素约 196k，触发 dense reconstruction 后 `_detect_lines` 产出 1660 条 raw lines、1169 条 merged lines，随后在 hub 估计阶段退化到不可接受耗时。
- 修复后验证：
  - `pytest -q tests/test_stroke_detector.py` -> 10 passed
  - `pytest -q tests/test_pipeline.py tests/test_stroke_detector.py` -> 23 passed
  - `python -X utf8 -m plot2svg.cli --input picture/end_to_end_flowchart.png --output outputs/end_to_end_flowchart --profile balanced --enhancement-mode auto` -> 成功生成 `final.svg`
- 当前输出质量结论：样本已可完成导出，但结构可编辑性仍有限；`scene_graph.json` 当前只有 `stroke_primitives=1`、`graph_edges=1`，同时 `raster_objects=21`，说明图中大量内容仍以 raster fallback 形式保留。
