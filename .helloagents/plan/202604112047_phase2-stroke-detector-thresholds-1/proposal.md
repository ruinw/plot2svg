# 方案包: phase2-stroke-detector-thresholds-1

```yaml
@feature: phase2-stroke-detector-thresholds-1
@created: 2026-04-11
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 2` 已经在 `graph_builder.py` 和 `detect_structure.py` 落了一批又一批阈值治理。下一步切到 `stroke_detector.py`，先处理一组高价值、测试覆盖最清晰的阈值：全局 sanity 过滤、最小 stroke 长度，以及 dense line reconstruction 触发条件。

### 目标
- 扩展 `ThresholdConfig`
- 将 `stroke_detector.py` 中以下阈值接入配置层：
  - `is_stroke_sane()` 的 canvas span / absurd width 判定
  - `_should_emit_stroke_primitive()` 的最小 polyline 长度
  - `_should_reconstruct_dense_lines()` 的主要触发阈值
- 保持默认行为不变

### 约束条件
- 本轮只处理这组三类阈值，不扩展到箭头头部几何或低对比度图像增强参数
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的节奏

### 验收标准
- `ThresholdConfig` 新增这组 stroke_detector 阈值字段
- 默认测试行为不变
- 可以通过自定义阈值改变：
  - 极宽 stroke 的 sane 判定
  - 短线段是否输出
  - dense reconstruction 是否触发
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“先接最上层筛选阈值”的最小闭环方案：

1. 在 `ThresholdConfig` 中新增 stroke_detector 第一批字段
2. 修改 `stroke_detector.py`
   - `detect_strokes()` 支持可选 `cfg`
   - `is_stroke_sane()`、`_should_emit_stroke_primitive()`、`_should_reconstruct_dense_lines()` 读取阈值
3. `pipeline.py` 调用 `detect_strokes(..., cfg=cfg, ...)`
4. 用最小测试验证：
   - 自定义阈值可让超宽 stroke 被接受
   - 自定义阈值可让短 stroke 输出
   - 自定义阈值可让 dense reconstruction 条件变化

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/stroke_detector.py`
- 修改: `src/plot2svg/pipeline.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_stroke_detector.py`

### 风险评估
- 风险 1: `detect_strokes()` 新增可选 `cfg` 后，若默认值处理不好，会影响已有大量测试
- 风险 2: 一次接过多局部图像处理阈值会让范围失控
- 风险 3: dense reconstruction 触发条件如果默认值漂移，会影响 fan 相关输出

### 关键决策
- 决策 ID: phase2-stroke-detector-thresholds-1#D001
- 决策: 第一批只接全局 sanity / 最小长度 / dense reconstruction 触发阈值，不碰箭头几何和图像增强阈值。
- 原因: 这组三类阈值最容易被现有测试可靠覆盖，也适合继续小批次推进。
