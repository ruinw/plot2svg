# 方案包: phase2-detect-shapes-thresholds-1

```yaml
@feature: phase2-detect-shapes-thresholds-1
@created: 2026-04-12
@type: implementation
@mode: R2
@selected_option: 2
```

## 1. 需求

### 背景
`Phase 2` 已经在 `graph_builder.py`、`detect_structure.py`、`stroke_detector.py` 和 `ocr.py` 落下了多批阈值治理。下一步切到 `detect_shapes.py`，先从最核心、最容易验证的轮廓分类阈值开始，不先碰 Hough 圆检测参数。

### 目标
- 扩展 `ThresholdConfig`
- 将 `detect_shapes.py` 中 contour classification 相关阈值接入配置层
- 保持默认行为不变

### 约束条件
- 本轮只处理 `classify_contour()` 的阈值，不扩展到 `detect_circles_hough()`
- 先补测试，再写实现，严格按 TDD 推进
- 继续沿用“隔离 worktree → 定向验证 → 合回 main → 全量测试”的节奏

### 验收标准
- `ThresholdConfig` 新增 detect_shapes 第一批阈值字段
- 默认测试行为不变
- 可以通过自定义阈值改变 contour classification 的结果
- 相关测试通过，合回 `main` 后全量测试通过

## 2. 方案

### 技术方案
采用“先接 contour classification 阈值”的最小闭环方案：

1. 在 `ThresholdConfig` 中新增 detect_shapes 的 contour classification 阈值字段
2. 在 `detect_shapes.py` 中新增一个轻量的阈值解析入口，让 `classify_contour()` 支持可选 `thresholds`
3. `contour_to_svg_element()` 也透传可选 `thresholds`
4. 暂不改 `detect_circles_hough()`，避免这轮范围扩散
5. 用最小测试验证：
   - 提高 rectangle fill 阈值可取消矩形分类
   - 提高 triangle solidity 阈值可取消三角形分类

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/detect_shapes.py`
- 修改: `tests/test_config.py`
- 修改: `tests/test_detect_shapes.py`

### 风险评估
- 风险 1: 这个模块会被 `segment.py`、`node_detector.py`、`region_vectorizer.py` 等复用，若默认值漂移会影响范围较广
- 风险 2: 若把 Hough 圆检测一并拉进来，这批范围会明显变大
- 风险 3: 轮廓测试样例必须选得足够简单，否则难以稳定验证阈值确实生效

### 关键决策
- 决策 ID: phase2-detect-shapes-thresholds-1#D001
- 决策: 第一批只接 contour classification 阈值，不处理 Hough circle 阈值。
- 原因: contour classification 这一组边界最清晰，也最适合继续小批次推进。
