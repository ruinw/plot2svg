# 任务清单: round27-outlier-pruning

```yaml
@feature: round27-outlier-pruning
@created: 2026-03-17
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 7/7 (100%) | 更新: 2026-03-17 11:36:00
当前: Round 27 已完成实现、定向测试与样例导出
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 7 | 0 | 0 | 7 |

---

## 任务列表

### 1. 测试约束与失败复现

- [√] 1.1 在 `tests/test_export_svg.py` 中补充模板 25px 膨胀区内数字/刻度文本清理测试 | depends_on: []
- [√] 1.2 在 `tests/test_graph_builder.py` 中补充 monster stroke 物理级熔断测试，覆盖面积/跨度/线宽三条规则 | depends_on: []
- [√] 1.3 在 `tests/test_pipeline.py` 中补充 `panel_arrow` 保留与不降级回归测试 | depends_on: []

### 2. 实现修复

- [√] 2.1 修改 `src/plot2svg/object_svg_exporter.py`，新增模板 bbox 25px padding 与数值型文本激进清理规则 | depends_on: [1.1]
- [√] 2.2 修改 `src/plot2svg/graph_builder.py`，在 edge 构建入口加入 monster stroke 硬熔断 | depends_on: [1.2]
- [√] 2.3 修改 `src/plot2svg/pipeline.py`，强化 `panel_arrow` 检测结果的 scene graph 保活与导出链路 | depends_on: [1.3]

### 3. 验证与产物

- [√] 3.1 运行 Round 27 目标测试并重跑样例，输出 `outputs/end_to_end_flowchart_round27/final.svg` 及相关调试产物 | depends_on: [2.1, 2.2, 2.3]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-17 11:17:14 | 方案包创建 | completed | 已按用户确认的方案 A 建立 Round 27 方案包 |
| 2026-03-17 11:36:00 | Round 27 开发实施 | completed | 已完成规则加固、定向测试通过，并生成 `outputs/end_to_end_flowchart_round27/final.svg` |

---

## 执行备注

- 本轮优先级顺序固定为：模板近邻数值文本清理 > monster stroke 熔断 > panel_arrow 召回保活。
- 仍然禁止通过阈值微调掩盖问题，所有修复都必须落在规则、语义或路由层。
- `outputs/end_to_end_flowchart_round27/` 为本轮默认样例输出目录。
