# 方案包: phase2-thresholds-graph-builder

```yaml
@feature: phase2-thresholds-graph-builder
@created: 2026-04-09
@type: implementation
@mode: R3
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 1` 的核心拆分已经完成，下一步进入 `Phase 2`。为了避免一次性把阈值治理铺得太散，这一批先落配置骨架，再把 `graph_builder.py` 中一组高影响、边界清晰的阈值接到配置层。

### 目标
- 在 `config.py` 中引入 `ThresholdConfig` 骨架
- 让 `PipelineConfig` 持有一份 profile 感知的阈值配置
- 将 `graph_builder.py` 中“monster stroke”判定相关硬编码阈值改为读取配置
- 保持默认行为不变

### 约束条件
- 本轮只处理 `config.py` 和 `graph_builder.py`
- 先补测试，再写实现，严格按 TDD 推进
- 第一批只接入一组核心阈值，不追求一次性消灭 `graph_builder.py` 的全部魔法数

### 验收标准
- `ThresholdConfig` 落地并挂入 `PipelineConfig`
- `graph_builder.py` 默认行为不变
- 可以通过自定义阈值改变 `graph_builder` 的 monster stroke 判定
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“配置骨架 + graph_builder 首批接入”的最小闭环方案：

1. 在 `config.py` 新增 `ThresholdConfig`
   - 第一批只纳入 `graph_builder` 的 monster stroke 判定阈值
   - 为 `speed` / `balanced` / `quality` 预留 profile override 结构
2. 修改 `PipelineConfig`
   - 新增 `thresholds` 字段
   - 默认按 `execution_profile` 自动构造阈值配置
3. 修改 `graph_builder.py`
   - `build_graph()` 支持可选接收 `PipelineConfig`
   - `_is_monster_stroke_primitive()` 改为读取 `cfg.thresholds`
   - `pipeline.py` 调用 `build_graph(scene_graph, cfg)`
4. 保持现有测试调用兼容
   - `build_graph(graph)` 仍可直接工作
   - 未显式传入配置时使用默认阈值

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/graph_builder.py`
- 修改: `src/plot2svg/pipeline.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_graph_builder.py`

### 风险评估
- 风险 1: `PipelineConfig` 增加阈值字段后，现有测试构造方式如果被破坏，会造成连锁失败
- 风险 2: `graph_builder` 默认阈值一旦偏移，会影响大量图边重建测试
- 风险 3: 这批如果把阈值接得太多，验证成本会快速膨胀

### 关键决策
- 决策 ID: phase2-thresholds-graph-builder#D001
- 决策: 第一批只接 `graph_builder` 的 monster stroke 判定阈值，不扩散到其它 snapping / routing 阈值
- 原因: 这组阈值语义最清晰，测试覆盖也最直接，适合做 Phase 2 的第一块落地。
