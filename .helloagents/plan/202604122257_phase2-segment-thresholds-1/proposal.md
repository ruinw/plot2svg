# 方案包: phase2-segment-thresholds-1

```yaml
@feature: phase2-segment-thresholds-1
@created: 2026-04-12
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 2` 已经把多轮阈值治理落到了 `graph_builder.py`、`detect_structure.py`、`stroke_detector.py`、`ocr.py` 和 `detect_shapes.py`。下一步切到 `segment.py`，先处理最核心、最容易验证的组件分类与最小面积阈值，不扩大到 proposal resize 或更深的分割策略。

### 目标
- 扩展 `ThresholdConfig`
- 将 `segment.py` 中 component role classification 与 minimum component area 的阈值接入配置层
- 保持默认行为不变

### 约束条件
- 本轮只处理 `classify_component_role()` 与 `_min_component_area()` 相关阈值
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的节奏

### 验收标准
- `ThresholdConfig` 新增 segment 第一批阈值字段
- 默认测试行为不变
- 可以通过自定义阈值改变 segment 的 role classification / min area 结果
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“先接分类和最小面积阈值”的最小闭环方案：

1. 在 `ThresholdConfig` 中新增 segment 第一批阈值字段
2. 在 `segment.py` 中新增一个轻量阈值解析入口，让 `classify_component_role()`、`_min_component_area()` 与 `compress_proposals()` 支持可选 `thresholds`
3. `propose_components()` 在入口统一解析阈值，并透传到 `_extract_records()` / `compress_proposals()`
4. 暂不处理 proposal resize、dense detail split、icon cluster 等更深层阈值，避免这轮范围扩散
5. 用最小测试验证：
   - 提高 text_like 的 aspect ratio 阈值可以改变分类结果
   - 提高 region 最小面积阈值可以过滤掉原本保留的小区域

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/segment.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_segment.py`

### 风险评估
- 风险 1: `segment.py` 位于较早阶段，默认值若漂移会影响下游多个模块
- 风险 2: 若一并拉入更多分割阈值，这批范围会明显失控
- 风险 3: 需要确保新增入口对现有调用保持兼容，避免把内部 helper 改成只能依赖 `PipelineConfig`

### 关键决策
- 决策 ID: phase2-segment-thresholds-1#D001
- 决策: 第一批只接 component role classification 与 minimum component area 阈值，不处理 proposal resize 和更深的 segment 细分阈值。
- 原因: 这一组边界最清晰，也最适合继续小批次推进。
