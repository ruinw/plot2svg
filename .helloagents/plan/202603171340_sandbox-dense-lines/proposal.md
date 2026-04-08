# 方案包: sandbox-dense-lines

```yaml
@feature: sandbox-dense-lines
@created: 2026-03-17
@type: implementation
@mode: R2
```

## 1. 需求

### 背景
用户要求在切片沙盒模式下，针对 `sandbox/A.png` 的高密度放射状连线结构做独立线条提取实验，禁止修改主项目代码，也禁止使用粗暴连通域轮廓把左侧密集区域拟合成实心黑块。

### 目标
- 新建独立脚本 `sandbox/sandbox_dense_lines.py`。
- 采用“骨架化 -> HoughLinesP 或等价线段检测 -> 端点合并”的线性降维流程。
- 暴露 `dilate_kernel`, `hough_threshold`, `min_line_length`, `max_line_gap` 等参数。
- 输出 `debug_01_skeleton.png`、`debug_02_extracted_lines.png`、`slice_A.svg`。
- 运行脚本并展示 `debug_02_extracted_lines.png`。

### 约束条件
- 严禁修改主项目核心代码。
- 仅允许修改 `sandbox/` 目录和当前方案包目录。
- 最终 SVG 必须以 `<line>` 为主，不走 `findContours` 的区域实心拟合路线。

### 验收标准
- 脚本成功运行。
- 生成 `sandbox/debug_01_skeleton.png`、`sandbox/debug_02_extracted_lines.png`、`sandbox/slice_A.svg`。
- `slice_A.svg` 中能看到大量 `<line>` 标签。

## 2. 方案

### 技术方案
- 输入仅固定为 `sandbox/A.png`。
- 用 alpha 合成白底后转灰度，并通过二值化与轻量膨胀增强线条连续性。
- 用形态学骨架化获得 1px 级骨架图。
- 在骨架图上运行 `cv2.HoughLinesP` 抽取线段，并按端点距离与方向相似度做一轮合并。
- 导出：
  - 骨架图 `debug_01_skeleton.png`
  - 原图叠加彩色线段 `debug_02_extracted_lines.png`
  - 纯 `<line>` 输出的 `slice_A.svg`

### 影响范围
- 新增: `sandbox/sandbox_dense_lines.py`
- 新增: `sandbox/test_sandbox_dense_lines.py`
- 新增产物: `sandbox/debug_01_skeleton.png`, `sandbox/debug_02_extracted_lines.png`, `sandbox/slice_A.svg`
