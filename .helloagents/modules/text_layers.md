# text_layers

职责:

- 从栅格图中分离 `text mask / text layer / graphic layer`
- 为后续图形矢量化提供去字后的 `graphic layer`

当前事实:

- 第六轮参考 `plotTosvg.zip` 后新增本模块，但只吸收了“文字先剥离”的预处理思路，没有引入其简单 contour 拼装主流程
- `separate_text_graphics(...)` 当前基于自适应阈值、形态学膨胀和 bbox 过滤生成文本掩膜
- `write_text_graphic_layers(...)` 会把 `*_text_mask.png`、`*_text_layer.png`、`*_graphic_layer.png` 写到输出目录，便于调试
- 当前策略是保守接入：`proposal` 仍使用原图，避免伤到 connector / fan 检测；`vectorize_region` 与 `vectorize_stroke` 改为优先读取 `graphic layer`
- 该模块的目标是减少文字对图形矢量化轮廓的干扰，不负责 OCR 本身
