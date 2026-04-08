# vectorize_region

职责:

- 将区域节点转成 SVG 区域元素

当前事实:

- 支持 `coordinate_scale`
- 第八轮起 `vectorize_regions(...)` 已从主实现降级为 legacy adapter
- 当前主流程会优先调用 `region_vectorizer.py` 生成 `RegionObject`
- `vectorize_regions(...)` 负责把 `RegionObject` 再包装回旧的 `RegionVectorResult`，维持旧测试和 fallback 导出兼容
- 使用增强图时会先按缩放裁切，再回到原图坐标尺度做区域对象与 SVG 输出
- 如果节点存在非白色 `fill`，会优先按填充颜色相似度生成区域掩膜，再提取 outer/holes
- 只有在对象级区域重建不可用时才回退到 `edges + threshold` 轮廓流程
- fallback path、primitive 输出都支持 `fill-opacity`
- 对带多个内部孔洞的复杂填充区域，会强制改用 `fill-rule='evenodd'` 路径输出，避免被错误简化为单个 `circle / ellipse`
- 2026-03-12 后，该兼容层同时接受对象层输出的椭圆与孔洞 path，不再把“少量几何孔洞区域”错误退化为矩形 fallback
