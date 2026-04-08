# region_vectorizer

职责:

- 以 mask-based、hole-aware 方式重建区域对象
- 在大型软容器上优先输出椭圆元数据，而不是锯齿 path

当前事实:

- 输入是图像与 `SceneGraph`
- 当前优先按节点的 `fill` 颜色相似度生成区域掩膜
- 椭圆拟合现在基于“填实后的最大外轮廓”，不再因为内部文字/连线孔洞直接放弃
- 椭圆判定会区分两类内部孔洞：
  - 文本/线条形成的 `irregular` 孔洞：允许继续拟合椭圆
  - 少量简单几何孔洞：保留 path + holes，避免误把复杂区域压成椭圆
- 输出为 `RegionObject`，核心字段包括：
  - `outer_path`
  - `holes`
  - `fill`
  - `fill_opacity`
  - `stroke`
  - `metadata.shape_type`
  - `metadata.ellipse`
- 该模块是第八轮后大型容器区域与复杂填充区域的主矢量化入口
- 2026-03-12 的 P0 收口后，`a22...png` 已能在对象层输出 2 个大型椭圆容器
