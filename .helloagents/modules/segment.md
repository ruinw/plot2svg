# segment

职责:

- 生成 `region / stroke / text_like` proposal
- 为明确几何节点提供早期 `shape_hint`
- 在 proposal 阶段做实例拆分与保守合并

当前事实:

- 第九轮起，`segment.py` 会对高填充、疑似多中心粘连 region 执行距离变换 + watershed 拆分
- 拆分触发条件刻意保守：低填充大容器、细长线状组件和小碎片不会被强行切开
- proposal 压缩阶段已新增几何对象保护：`triangle / pentagon / circle` 这类显式几何 hint 不再按旧的 `0.82` 激进重叠阈值直接合并
- contour 级 `shape_hint` 目前只稳定产出 `triangle / pentagon`；圆形 hint 仍优先依赖 Hough 注入，避免在低分辨率样本上制造假圆
- 在主样本 `a22...png` 上，proposal 层现可保留 `triangle / pentagon / circle` 混合几何提示，不再只有 circle
