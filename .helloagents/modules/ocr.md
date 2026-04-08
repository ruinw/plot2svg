# ocr

职责:

- 合并相邻文本框
- 对文本节点执行 OCR

当前事实:

- OCR 支持 `coordinate_scale`
- 当 vector source 是超分图时，会先按缩放关系裁切，再缩回原图坐标尺度供 OCR 使用
