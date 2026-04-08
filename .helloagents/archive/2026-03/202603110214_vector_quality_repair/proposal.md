# 方案: vector_quality_repair

## 背景

用户反馈经过多轮优化后，导出的 SVG 仍有明显识别错误，并且视觉上与原图相差很大，需要使用 `./picture` 中样本做系统修复。

第二轮用户明确要求：

- 视觉还原优先
- 优先保留填充颜色、半透明区域、圆形/网络结构和整体布局
- 接受可编辑性略弱于此前版本

## 第一轮根因

1. 小图超分后，proposal / OCR / vectorize 没有共享同一坐标系。
2. `signature_lineart` 路由过度依赖文件名。
3. Hough 圆形注入缺少足够的局部验证。

## 第二轮根因

1. region 节点默认白底黑边，输出天然偏向黑白轮廓稿。
2. region 没有从原图恢复 fill / stroke / transparency。
3. region vectorize 更偏向边缘稿，而不是填充区域本身。

## 实施方案

### 第一轮

1. 保持 proposal 以原图坐标系为准。
2. 给 OCR 与 vectorize 增加 `coordinate_scale`，正确使用增强图。
3. 将签名路由改为“文件名提示 + 内容校验”。
4. 给圆形注入增加局部轮廓验证。
5. 补充针对小图坐标越界、缩放 OCR、缩放 vectorize 和样本回归的测试。

### 第二轮

1. 在 `scene_graph` 中为 region 节点从原图抽样 `fill / stroke / fill_opacity`。
2. 在 `pipeline` 中接入样式富化流程。
3. 在 `vectorize_region` 中优先提取填充区域轮廓。
4. 在 `detect_shapes` 中为 SVG 原语统一支持 `fill-opacity`。
5. 增加主样本视觉回归测试，确保非黑白填充、透明度和圆形原语存在。

## 验收

- `pytest -q` 全绿
- `./picture` 全样本可跑通
- `orr_signature.png` 节点 bbox 全部落在画布内
- `F2.png` 的 `circle` hint 显著下降
- 主样本导出结果必须包含非黑白 fill、透明度和足够数量的圆形原语
