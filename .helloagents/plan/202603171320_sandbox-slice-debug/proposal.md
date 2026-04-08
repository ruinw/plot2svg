# 方案包: sandbox-slice-debug

```yaml
@feature: sandbox-slice-debug
@created: 2026-03-17
@type: implementation
@mode: R2
```

## 1. 需求

### 背景
用户要求进入隔离沙盒模式，仅在 `sandbox` 目录内复现实验，不允许修改主项目核心代码。需要对切片图片进行局部图像处理试验，暴露 OpenCV 参数，并输出每个关键步骤的视觉日志与最终 `slice_result.svg`。

### 目标
- 仅在 `sandbox` 目录内创建独立 Python 脚本。
- 自动读取沙盒中的切片图片，执行局部图像处理。
- 将阈值、核大小、迭代次数、Canny 边界等参数提升为脚本顶部全局变量。
- 强制输出灰度图、二值掩膜、形态学结果、轮廓预览。
- 生成 `sandbox/slice_result.svg` 并立即运行脚本验证。

### 约束条件
- 不修改 `pipeline.py`、`graph_builder.py`、`object_svg_exporter.py` 等主线核心文件。
- 所有调试产物只落在 `sandbox/` 目录。
- 在用户明确“验证通过，允许合并”前，不把任何沙盒逻辑移植回主线。

### 验收标准
- `sandbox/sandbox_test.py` 成功运行。
- 生成 `sandbox/debug_01_grayscale.png`、`sandbox/debug_02_binary_mask.png`、`sandbox/debug_03_morphology.png`、`sandbox/debug_04_contours.png`。
- 生成 `sandbox/slice_result.svg`。
- 返回运行结果与输出文件清单。

## 2. 方案

### 技术方案
- 使用独立脚本扫描 `sandbox/` 下的切片图片，跳过已有调试产物。
- 对每张切片统一做：Alpha 合成到白底 → 灰度 → 自适应/固定阈值二值化 → 形态学闭/开操作 → Canny 边缘辅助 → 轮廓提取。
- 以拼图形式导出四张调试总览图，便于用户直接查看。
- 将过滤后的轮廓转换为简化 SVG path，并输出合并版 `slice_result.svg`。

### 影响范围
- 新增: `sandbox/sandbox_test.py`
- 可选新增: `sandbox/test_sandbox_test.py`
- 新增产物: `sandbox/debug_*.png`, `sandbox/slice_result.svg`

### 风险评估
- 切片内容差异较大时，统一参数可能无法同时适配；通过顶部全局变量暴露，便于后续微调。
- 轮廓法可能对半透明像素敏感；通过白底合成减少 alpha 干扰。
