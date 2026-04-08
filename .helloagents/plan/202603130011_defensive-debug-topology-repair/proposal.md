# 变更提案: defensive-debug-topology-repair

## 元信息
`yaml
类型: 修复/重构
方案类型: implementation
优先级: P0
状态: 已确认
创建: 2026-03-13
`

---

## 1. 需求

### 背景
Round 12 人工验收表明，Round 11 仍存在三类阻断性缺陷：
- 文本或 OCR bounding box 被实体化为 region/path，甚至遮挡画面。
- Polygenic 放射状细线在 proposal 阶段被吞并为单个大 region，最终坍塌成黑色巨三角。
- Omnigenic 内部低对比连线仍大量缺失，箭头头部在 stroke 导出中被放大为夸张黑块。

### 目标
- 彻底禁用 bbox 直接实体化为 RegionObject 或 path fallback。
- 将高密度细线簇从 egion 主链中剥离，优先进入 stroke 主链。
- 重构低对比线条检测与箭头尺寸逻辑，恢复内部拓扑并限制箭头面积。
- 强制输出 debug_lines_mask.png 与 debug_region_segmentation.png，作为中间态验收依据。
- 使用 picture/a22efeb2-370f-4745-b79c-474a00f105f4.png 与 picture/F2.png 重新导出最新 SVG 和 debug 图。

### 约束条件
`yaml
性能约束: 继续使用 OpenCV/NumPy classical CV，不引入外部深度模型
环境约束: 当前环境无 cv2.ximgproc / scipy / skimage，骨架化需项目内实现或采用等效保守分流
兼容性约束: 不破坏现有 SceneGraph / RegionObject / StrokePrimitive / GraphEdge 数据接口
调试约束: 本轮必须落盘并验收 2 张 debug 图片
`

### 验收标准
- [ ] bbox / text box 不再出现在最终 SVG 的 region/path 实体中。
- [ ] Polygenic 放射线不再以单个黑色大三角输出。
- [ ] Omnigenic 内部低对比线条在 debug_lines_mask.png 中可见，且最终 SVG 中恢复主要拓扑。
- [ ] debug_region_segmentation.png 中背景与文本框不被着色为实体，放射线簇不被涂成单块 region。
- [ ] 输出最新 .svg、debug_lines_mask.png、debug_region_segmentation.png。
- [ ] 全量 pytest -q 通过。

---

## 2. 方案

### 技术方案
采用“防御式分流修复”方案：
1. segment.py 增加 bbox/文本框/细线簇防御门禁，并输出区域分割调试图。
2. egion_vectorizer.py 禁止矩形 bbox fallback 实体化，凡无真实实体轮廓的一律标记无效。
3. pipeline.py 调整 proposal 的文本输入源，避免 OCR 文本框再次回流到 proposal 主链。
4. stroke_detector.py 引入细线增强、轻量骨架化/细化分流、箭头头部尺寸上限，并输出线条掩膜调试图。
5. 先写失败测试，再做最小实现，最后跑真实样本和全量回归。

### 影响范围
`yaml
涉及模块:
  - src/plot2svg/segment.py
  - src/plot2svg/region_vectorizer.py
  - src/plot2svg/stroke_detector.py
  - src/plot2svg/pipeline.py
  - src/plot2svg/object_svg_exporter.py
  - tests/test_segment.py
  - tests/test_region_vectorizer.py
  - tests/test_stroke_detector.py
  - tests/test_pipeline.py
预计变更文件: 9
`

### 风险评估
| 风险 | 等级 | 应对 |
|------|------|------|
| 过度分流导致真实填充 region 被误降为 stroke | 中 | 只对极端细长、高孔隙率、高密度线簇触发分流 |
| 轻量骨架化带来断线 | 中 | 保留原 mask 与细化 mask 双通道，取连通性更优结果 |
| 禁用 bbox fallback 后部分 region 直接消失 | 中 | 明确标记无效并用 debug 图验证，而不是静默生成矩形 |
| debug 输出污染正式产物目录 | 低 | 统一写入本轮输出目录，文件名固定 |

---

## 3. 技术设计

### 核心数据流
`mermaid
flowchart TD
    A[input image] --> B[text mask separation]
    B --> C[proposal segmentation]
    C --> D{dense stroke cluster?}
    D -- yes --> E[stroke candidate path]
    D -- no --> F[region candidate path]
    F --> G[region validity gate]
    G -- invalid --> H[drop / debug only]
    G -- valid --> I[RegionObject]
    E --> J[adaptive + contrast + thinning]
    J --> K[StrokePrimitive]
    C --> L[debug_region_segmentation.png]
    J --> M[debug_lines_mask.png]
`

### 关键决策
- 禁止任何 cv2.boundingRect 直接成为 region 几何输出，仅允许其作为统计特征。
- 对细线簇优先做 stroke 分流，而不是让 egion_vectorizer 再去猜测。
- 箭头头部尺寸必须受局部线宽和端点邻域上限约束，不能随 blob 面积线性膨胀。