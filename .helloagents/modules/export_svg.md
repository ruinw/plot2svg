# export_svg

职责:

- 汇总 scene graph、region 结果与 stroke 结果，输出最终 SVG

当前事实:

- 第八轮前会优先按 group 输出结构化 `<g>`
- region fragment 中的颜色和 `fill-opacity` 会原样保留到最终 SVG
- 文本节点仍以 `<text>` 输出，填充区域和连接线继续保持分组信息
- `shape_type='fan'` 的 group 会走专用扇形导出逻辑，重建汇聚线束而不是直接复用原始大 `stroke`
- 第四轮起会优先读取 group 关联的 `SceneRelation`，对 `fan` 结构走 relation-first 导出
- 第五轮起 `connector` relation 也会走 relation-first 导出：根据 `source_ids / target_ids` 重新生成干净连接线，而不是继续直接复用裸 `stroke`
- 当 connector group 被标记为 `shape_type='arrow'` 时，导出层会补一个简化箭头头部 polygon
- 导出结果会补充 `data-relation-id` 与 `data-relation-type`，用于回归验证连接结构是否被正确重建
- 第七轮起若某个 group 命中对象层映射，导出结果还会补充 `data-object-id` 与 `data-object-type`
- 第八轮起 exporter 会优先切到 `object_svg_exporter.py`：
  - `regions`
  - `edges`
  - `nodes`
  - `text`
- object-driven edge 现在会输出 `class='edge'`，并继续补充 `data-relation-type='connector'` 以保持历史回归兼容
- `fan` 兼容导出未删除；在 object-driven 模式下仍会补一层 fan `<g>`，避免第四轮能力回退
- 当前导出层已经进入 object-driven geometry export，但仍保留 fallback region/stroke fragment 以兜住尚未显式建模的装饰图元
