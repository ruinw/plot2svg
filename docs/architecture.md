# Plot2SVG Architecture

## 目标

Plot2SVG 的目标不是简单做 `image trace`，而是建立一条可控的处理链：

```text
PNG -> 输入画像 -> 增强 -> 组件提议 -> scene graph -> 矢量化 -> SVG
```

核心要求有两个：

- 低质量输入先变得更可解析
- 输出结果必须接近“按组件编辑”，而不是单层路径堆叠

## 总体流水线

### 1. `analyze.py`

负责读取输入基本信息，并给出路由判断：

- `small_lowres`
- `wide_hires`
- `signature_lineart`
- `flat_graphics`

这一步会写出 `analyze.json`。

### 2. `enhance.py`

负责图像预处理：

- 去噪
- 对比度增强
- 轻锐化
- 保守上采样

产物：

- `enhanced.png`
- `enhance.json`

### 3. `segment.py`

负责组件提议，是当前 CPU 侧最重的阶段之一。

当前策略：

- 普通图片：直接提议
- 宽图：先降采样做主提议
- 宽图文本：再走原图文本补提议
- 最后统一做 proposal 压缩与去碎片

输出：

- `components_raw.json`
- `masks/*.png`

proposal 类型：

- `region`
- `stroke`
- `text_like`

### 4. `scene_graph.py`

负责将 proposal 转为统一中间表示。

这是整个系统最重要的协议层。当前节点类型包括：

- `background`
- `region`
- `stroke`
- `text`

`scene_graph.json` 是后续导出、重排、编辑和质量分析的事实源。

### 5. `ocr.py`

负责把 `text` 节点升级成带文字内容的节点。

当前能力：

- 文本框合并
- 多候选择优
- 多行文本 fallback
- 自动优先使用 GPU OCR

### 5.5. `detect_structure.py`

负责在 scene graph 组上标注结构语义。位于 `promote_component_groups()` 之后、序列化之前。

检测能力：

- **Box 分类**：`labeled_region` / `labeled_component` 含 text 子节点且 region 宽高比 < 6.0 → `shape_type="box"`
- **Arrow 分类**：`connector` 组自动标记 `shape_type="arrow"`，根据宽高比判定 `direction`（"right" / "down"）
- **Container 检测**：从未分组的大 region 节点中发现包含 ≥2 个现有组的容器，创建 `role="container"` 组

纯几何启发式，无重模型依赖。

### 6. `vectorize_region.py`

负责把 `region` 节点转换成区域轮廓路径。

特点：

- 基于真实图像区域
- 使用轮廓提取
- OpenCV 异常时回退到保守矩形路径

### 7. `vectorize_stroke.py`

负责把 `stroke` 节点转换成线稿/笔画路径。

特点：

- 基于真实图像区域
- 二值化 + 轮廓/折线提取
- 适合签名与细线条样本

### 8. `export_svg.py`

负责将 `scene_graph` 与矢量化结果组装成最终 SVG。

当前导出内容：

- `region` -> `<path>`
- `stroke` -> `<path>`
- `text` -> `<text>`

## 配置与模式

### `PipelineConfig`

当前配置项包括：

- `enhancement_mode`
- `execution_profile`
- `tile_size`

### 三档模式

#### `speed`

- 更激进的提议降采样
- 更少 OCR 变体
- 更严格的小文本框跳过

#### `balanced`

- 默认模式
- 适合作为普通开发和调试基线

#### `quality`

- 更大的 proposal 提议尺寸
- 更宽松的文本框保留
- 更多 OCR 变体

## 当前瓶颈

### 1. CPU 瓶颈

主要来自：

- 宽图组件提议
- 区域轮廓提取
- 大量文本节点的 OCR

### 2. 质量瓶颈

主要来自：

- 文本框仍可能碎裂
- OCR 会出现识别错误
- 区域 proposal 仍然偏视觉级，而不完全是语义级

## 当前权衡

系统现在已经能在速度和质量之间切换，但还没有做到两者同时最优。

典型 tradeoff：

- 更快的宽图提议
  - 提升速度
  - 可能损失细文本
- 更强的文本补提议和 OCR
  - 提升文本恢复
  - 增加总耗时

## 推荐阅读顺序

如果你要继续开发，建议按这个顺序读代码：

1. `src/plot2svg/config.py`
2. `src/plot2svg/pipeline.py`
3. `src/plot2svg/segment.py`
4. `src/plot2svg/ocr.py`
5. `src/plot2svg/scene_graph.py`

## 后续演进方向

### 短期

- 真实 `preview.png`
- 更稳的文本分行/段落重建
- 宽图更细粒度的补提议策略

### 中期

- scene graph 节点的图标/背景/箭头等语义扩展
- 更稳定的文本内容校正
- 批处理与回归基准

### 长期

- 交互式组件纠错
- DrawIO/PPTX 等更多目标格式
- 语义级组件编辑而不是仅几何级编辑
