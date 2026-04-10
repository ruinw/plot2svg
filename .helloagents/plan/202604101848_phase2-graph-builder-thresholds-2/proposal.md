# 方案包: phase2-graph-builder-thresholds-2

```yaml
@feature: phase2-graph-builder-thresholds-2
@created: 2026-04-10
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
上一批 `Phase 2` 已经让 `ThresholdConfig` 落地，并把 `graph_builder.py` 中 monster stroke 判定接入配置层。下一步继续处理 `graph_builder.py` 中更高频、测试覆盖更集中的一组阈值：端点吸附、单边边过滤、文本簇相邻过滤。

### 目标
- 扩展 `ThresholdConfig`
- 将 `graph_builder.py` 中以下阈值接入配置层：
  - partial edge 修复和丢弃阈值
  - one-sided text edge 过滤阈值
  - text cluster 相邻过滤阈值
  - direct/gap snap 基础阈值
- 保持默认行为不变

### 约束条件
- 本轮只处理这一组高价值阈值，不扩散到 routing 细节或其它模块
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的节奏

### 验收标准
- `ThresholdConfig` 新增这组 graph_builder 阈值字段
- 默认测试行为不变
- 可以通过自定义阈值改变：
  - near miss 的吸附结果
  - 短 partial edge 的保留/丢弃结果
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“继续扩展同一配置对象”的最小改动路径：

1. 在 `config.py` 的 `ThresholdConfig` 中新增这组 graph_builder 阈值字段。
2. 在 `graph_builder.py` 中把这组 helper 改为接收 `thresholds`：
   - `_repair_partial_edge_anchors`
   - `_should_drop_partial_edge`
   - `_should_drop_adjacent_text_cluster_link`
   - `_should_drop_weak_one_sided_edge`
   - `_nearest_anchor`
   - `_direct_snap_limit`
   - `_gap_snap_limit`
3. 保持 `build_graph(graph, cfg=None)` 兼容现有调用。
4. 用最小测试验证自定义阈值确实能改变行为，而不是只验证字段存在。

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/graph_builder.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_graph_builder.py`

### 风险评估
- 风险 1: 一次性接太多 routing 细节阈值，会让范围失控
- 风险 2: 这些 helper 链路比较深，漏传 `thresholds` 容易导致默认行为与自定义行为混乱
- 风险 3: 如果测试样例选得不好，可能看不出自定义阈值是否真的生效

### 关键决策
- 决策 ID: phase2-graph-builder-thresholds-2#D001
- 决策: 本轮只接端点吸附、partial edge 过滤和 text cluster 相邻过滤这一组，不碰更深层 routing 阈值。
- 原因: 这组阈值测试边界最清晰，也最适合继续沿小批次推进。
