# analyze

职责:

- 读取输入尺寸和基础属性
- 选择 `wide_hires / small_lowres / flat_graphics / signature_lineart` 路由

当前事实:

- `signature_lineart` 不再只看文件名
- 当文件名包含 `signature` 或 `sign` 时，还会检查图像是否同时满足低饱和度和低深色覆盖率
