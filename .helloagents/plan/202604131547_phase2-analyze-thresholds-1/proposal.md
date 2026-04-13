# 方案包: phase2-analyze-thresholds-1

```yaml
@feature: phase2-analyze-thresholds-1
@created: 2026-04-13
@type: implementation
@mode: R2
@selected_option: 1
```

## 1. 需求

### 背景
`Phase 2` 已经把主要阈值治理推进到了 `graph_builder.py`、`detect_structure.py`、`stroke_detector.py`、`ocr.py`、`detect_shapes.py` 和 `segment.py`。当前剩余模块里，`analyze.py` 仍保留少量决定路由的硬编码阈值。

### 目标
- 扩展 `ThresholdConfig`
- 将 `analyze.py` 中路由判断与签名图判断相关阈值接入配置层
- 保持默认行为不变

### 约束条件
- 本轮只处理 route selection 与 signature line-art detection 阈值
- 不纳入 `should_tile`、`should_super_resolve` 或指标缩放常量
- 先补测试，再写实现，严格按 TDD 推进

### 验收标准
- `ThresholdConfig` 新增 analyze 第一批阈值字段
- 默认测试行为不变
- 可以通过自定义阈值改变 analyze 的 route 结果
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“只接路由判断 + 签名图判断”的最小闭环方案：

1. 在 `ThresholdConfig` 中新增 analyze 第一批阈值字段
2. 让 `analyze_image()` 支持可选读取 `PipelineConfig` 中的阈值
3. `pipeline.py` 在调用 `analyze_image()` 时透传现有 `cfg`
4. `_choose_route()` 与 `_looks_like_signature_lineart()` 改为读取可选阈值
5. 用最小测试验证：
   - 调高 small route 阈值可以把默认 `flat_graphics` 变成 `small_lowres`
   - 放宽 signature dark-ratio 阈值可以把默认非签名路由变成 `signature_lineart`

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/analyze.py`
- 修改: `src/plot2svg/pipeline.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_analyze.py`

### 风险评估
- 风险 1: `analyze.py` 位于 pipeline 最前面，默认值漂移会影响后续整个处理路径
- 风险 2: 如果把 tiling / super-resolution 一并拉入，这轮范围会明显变大
- 风险 3: 需要保持现有测试调用兼容，不能强迫所有调用方都显式传 `cfg`

### 关键决策
- 决策 ID: phase2-analyze-thresholds-1#D001
- 决策: 第一批只接 route selection 与 signature line-art detection 阈值，不处理 tiling / super-resolution 判定阈值。
- 原因: 这一组最容易验证，也最适合把 `Phase 2` 平稳收尾。
