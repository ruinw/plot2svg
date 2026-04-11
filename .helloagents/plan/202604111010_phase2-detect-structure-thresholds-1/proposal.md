# 方案包: phase2-detect-structure-thresholds-1

```yaml
@feature: phase2-detect-structure-thresholds-1
@created: 2026-04-11
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 2` 在 `graph_builder.py` 已经推进了多批，下一步切到 `detect_structure.py`。为了继续保持小批次节奏，这一轮先只处理 box / arrow / fan 这一组结构阈值，暂时不碰容器检测。

### 目标
- 扩展 `ThresholdConfig`
- 将 `detect_structure.py` 中 box / arrow / fan 相关阈值接入配置层
- 保持默认行为不变

### 约束条件
- 本轮只处理 box / arrow / fan 相关阈值
- 先补测试，再写实现，严格按 TDD 推进
- 保持 `detect_structures(scene_graph)` 现有调用兼容，必要时通过可选 `cfg` 接线

### 验收标准
- `ThresholdConfig` 新增这组 detect_structure 阈值字段
- 默认测试行为不变
- 可以通过自定义阈值改变 box / arrow / fan 的结构识别行为
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“第一批先接最明显几组几何阈值”的最小闭环方案：

1. 在 `ThresholdConfig` 中新增 detect_structure 的 box / arrow / fan 阈值字段
2. 修改 `detect_structure.py`
   - `detect_structures()` 支持可选 `cfg`
   - `_is_box_shape()`、`_classify_arrows()`、`_detect_fans()`、`_find_fan_target()`、`_nearest_anchor()` 读取阈值
3. `pipeline.py` 改为调用 `detect_structures(scene_graph, cfg)`
4. 用最小测试验证：
   - 调高 box 宽高比阈值可以把细长框识别成 box
   - 调高 arrow 宽高比阈值会取消箭头方向判定
   - 调低 fan 最小源节点数会放宽 fan 检测

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/detect_structure.py`
- 修改: `src/plot2svg/pipeline.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_detect_structure.py`

### 风险评估
- 风险 1: `detect_structures()` 新增可选 `cfg` 后，若默认值处理不好，会影响大量现有测试
- 风险 2: 一次接太多 fan 细节阈值会导致断言脆弱
- 风险 3: 容器检测和 fan 检测都在这个模块里，本轮必须刻意避免范围扩散

### 关键决策
- 决策 ID: phase2-detect-structure-thresholds-1#D001
- 决策: 第一批只接 box / arrow / fan 阈值，不处理 container 阈值。
- 原因: 这几组最容易被现有测试覆盖，也最适合继续小批次推进。
