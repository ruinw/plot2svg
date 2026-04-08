# detect_structure

职责:

- 对 scene graph 做二次结构识别
- 为导出层补充 box / arrow / container / fan 等结构语义

当前事实:

- 已支持 `box`、`arrow`、`container`
- 第三轮新增 `fan` 检测，用于识别“多圆点源节点 + 汇聚线束 + 目标框”的扇形结构
- `fan` 检测会给相关节点补充 `group_id` 和 `component_role`
- 第四轮起 `fan` 检测会同时写入 `SceneRelation(relation_type='fan')`
- 第五轮已新增普通 connector relation 检测：对 `group.role == 'connector'` 的候选会生成 `SceneRelation(relation_type='connector')`
- connector relation 当前至少包含 `source_ids / target_ids / backbone_id / group_id / metadata(direction, shape_type)`
- source / target 锚定目前基于 connector 两端点与邻近 region/text 的最近邻启发式，属于最小可用方案
- 第七轮起 box 分类会读取 `SceneObject` 元数据：
  - 若主 region 属于 `network_container` 或 `cluster_region`
  - 则该 group 不再被标成普通 `box`
- 第八轮起 `detect_structure.py` 的定位调整为“兼容结构层”：
  - 保留 `fan / connector / box / container` 兼容识别
  - 继续为老的 relation-first 回归提供结构语义
  - 但新的 `graph edge` 主锚定已迁移到 `graph_builder.py`
- 当前策略已从“object metadata + group 兼容 + relation 增量接入”升级为“object-driven 主链 + group/relation 兼容层并存”
