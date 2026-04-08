# 方案说明: sandbox-line-refinement

## 目标

在不修改主项目核心代码的前提下，对 `sandbox/slice_A_v2.svg` 中的碎片化路径做独立重构，输出更接近原图放射结构的 `slice_A_v3.svg`，并生成带几何中心标注的调试图。

## 范围

- 仅操作 `sandbox/` 下的输入与输出文件
- 新增独立脚本 `sandbox_line_refinement.py`
- 新增对应回归测试
- 生成 `debug_04_refined_structure.png` 与 `slice_A_v3.svg`

## 实现思路

- 读取 `slice_A_v2.svg` 中的 polyline/path 坐标
- 通过端点自动吸附合并近距离碎片
- 对近似共线的拼接结果做直线回归，抹平像素抖动
- 用长线段估计放射中心，将碎片重新归并为少量径向主干
- 使用 RDP 抽稀并导出 `<path>` 形式的 SVG

## 验收标准

- 生成 `sandbox/debug_04_refined_structure.png`
- 生成 `sandbox/slice_A_v3.svg`
- 输出路径数显著低于 `slice_A_v2.svg`，目标少于 20 条，兜底不得高于 30 条
- 全流程仅发生在沙盒，不回写主线
