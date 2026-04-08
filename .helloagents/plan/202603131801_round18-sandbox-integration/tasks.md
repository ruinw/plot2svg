# 任务清单: round18-sandbox-integration

```yaml
@feature: round18-sandbox-integration
@created: 2026-03-13
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 5/5 (100%) | 更新: 2026-03-13 18:52:00
当前: 已完成主干集成与定向验证
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 5 | 0 | 0 | 5 |

---

## 任务列表

### 1. 方案包与基线

- [√] 1.1 完成 `proposal.md` 和 `tasks.md`，记录最小侵入集成方案
- [√] 1.2 审核主干与 sandbox 差异，锁定需要移植的函数和测试点

### 2. 高密度线束重建

- [√] 2.1 在 `src/plot2svg/stroke_detector.py` 中接入密集线束专用重建逻辑
- [√] 2.2 在 `src/plot2svg/graph_builder.py` 中修正多 primitive 场景的 edge id 与回填兼容

### 3. 复杂图标降级

- [√] 3.1 新增共享 `IconProcessor` helper，并抽离复杂度评估/Base64 编码逻辑
- [√] 3.2 在 `src/plot2svg/pipeline.py` 中复用 helper，继续输出 `RasterObject`

### 4. 导出顺序与测试

- [√] 4.1 在 `src/plot2svg/object_svg_exporter.py` 中修正导出层级顺序
- [√] 4.2 更新 `tests/test_stroke_detector.py`、`tests/test_pipeline.py`、`tests/test_export_svg.py`

### 5. 验证

- [√] 5.1 运行定向 pytest 与端到端渲染，确认输出满足 Round18 目标

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-13 18:40:00 | 1.1 | completed | 已补齐方案包并固化最小侵入集成决策 |
| 2026-03-13 18:44:00 | 2.1/2.2 | completed | 新增密集线束重建 helper，并修正多 primitive edge id |
| 2026-03-13 18:46:00 | 3.1/3.2 | completed | 新增 `IconProcessor` 并接入 `pipeline` 的 raster fallback |
| 2026-03-13 18:48:00 | 4.1/4.2 | completed | 完成导出层级调整并补齐相关测试 |
| 2026-03-13 18:52:00 | 5.1 | completed | 定向 pytest 通过，`picture/` 样例完成端到端渲染 |

---

## 执行备注

> 本轮采用最小侵入集成：保留 `RasterObject`，不新增 `IconObject`；高密度线束通过多 `StrokePrimitive` 输出恢复线性语义。
