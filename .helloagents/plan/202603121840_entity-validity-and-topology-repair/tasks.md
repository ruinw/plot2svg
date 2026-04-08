# 任务清单: entity-validity-and-topology-repair

```yaml
@feature: entity-validity-and-topology-repair
@created: 2026-03-12
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 6/6 (100%) | 更新: 2026-03-12 20:36:00
当前: 已完成真实样本回归、全量测试与知识库同步
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 6 | 0 | 0 | 6 |

---

## 任务列表

### 1. 测试约束

- [√] 1.1 在 `tests/test_region_vectorizer.py` 中新增幽灵碎片过滤与有效实体判定测试 | depends_on: []
- [√] 1.2 在 `tests/test_stroke_detector.py` 中新增淡色背景低对比网络线恢复测试 | depends_on: []
- [√] 1.3 在 `tests/test_text_layers.py` 与 `tests/test_export_svg.py` 中新增文本蒙版不切底图、无效 region 不导出测试 | depends_on: []

### 2. 实现修复

- [√] 2.1 在 `src/plot2svg/segment.py` 与 `src/plot2svg/region_vectorizer.py` 中实现有效实体过滤与背景残渣抑制 | depends_on: [1.1]
- [√] 2.2 在 `src/plot2svg/text_layers.py` 中收紧文本蒙版链路，并保持 `pipeline.py` 的 region/original、stroke-node/graphic 分层输入 | depends_on: [1.3]
- [√] 2.3 在 `src/plot2svg/stroke_detector.py` 中实现 adaptive 主路径、blackhat 增强与噪声过滤 | depends_on: [1.2]

### 3. 回归验证

- [√] 3.1 运行 `picture/a22...png`、`picture/F2.png` 和全量 `pytest -q`，并更新知识库文档 | depends_on: [2.1, 2.2, 2.3]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-12 18:45:00 | 方案包创建 | completed | 已按方案A生成 proposal/tasks |
| 2026-03-12 19:56:00 | 定向失败测试复现 | completed | 锁定 `entity_valid` 缺失、`adaptive` 非主路径、invalid region 未屏蔽 |
| 2026-03-12 20:08:00 | P0/P1 代码修复 | completed | 完成 `region_vectorizer` / `stroke_detector` / `object_svg_exporter` / `text_layers` / `segment` 收敛 |
| 2026-03-12 20:13:00 | 定向测试回归 | completed | `tests/test_region_vectorizer.py`、`tests/test_stroke_detector.py`、`tests/test_text_layers.py`、`tests/test_export_svg.py` 全部通过 |
| 2026-03-12 20:18:00 | 真实样本导出 | completed | 生成 `outputs/round11_a22_balanced/final.svg` 与 `outputs/round11_f2_balanced/final.svg` |
| 2026-03-12 20:31:00 | 全量测试 | completed | `134 passed, 1 warning` |
| 2026-03-12 20:36:00 | 知识库同步 | completed | 更新 `context.md`、`CHANGELOG.md` 与当前任务状态 |

---

## 回归摘要

- `outputs/round11_a22_balanced/scene_graph.json`
  - `region_objects=16`
  - `invalid_regions=1`
  - `stroke_primitives=16`
  - `graph_edges=16`
- `outputs/round11_f2_balanced/scene_graph.json`
  - `region_objects=35`
  - `invalid_regions=0`
  - `stroke_primitives=186`
  - `graph_edges=186`
- 全量测试：`134 passed, 1 warning`

## 执行备注

- 本轮优先级按用户反馈执行：`stroke_detector.py` 与 `region_vectorizer.py` 为 P0，`text_layers.py` 为必要 P1 收敛。
- `segment.py` 的“全屏兜底 proposal”已经收紧为仅在完全无 proposal 时触发，避免真实样本继续引入背景实体。
- `node_detector.py` 的星形模板匹配仍保留为后续 P2，当前未在本轮展开。