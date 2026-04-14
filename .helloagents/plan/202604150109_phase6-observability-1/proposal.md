# 方案包: phase6-observability-1

```yaml
@feature: phase6-observability-1
@created: 2026-04-15
@type: implementation
@mode: R3
@selected_option: 1
```

## 1. 需求

### 背景
`Phase 6` 目标是提高可观测性。当前主要问题是 CLI 仍使用 `print()`，pipeline 缺少阶段日志，`scene_graph.json` 没有摘要统计，debug 图片输出也没有统一开关。

### 目标
- 用标准日志替换 CLI 输出
- 在 pipeline 各阶段增加日志与耗时记录
- 在 `scene_graph.json` 中增加摘要信息
- 让 CLI 的 `--verbose` 控制 debug 图片输出

### 约束条件
- 保持现有 pipeline 默认测试行为稳定
- 先补测试，再写实现，严格按 TDD 推进
- 不扩展到更大范围的 logging 框架重构

### 验收标准
- `cli.py` 不再使用 `print()`
- `build_parser()` 支持 `--verbose`
- `SceneGraph.to_dict()` 含摘要字段
- OCR 异常路径会输出 warning 而不是静默吞掉
- pipeline 可根据配置决定是否输出 debug 图片

## 2. 方案

### 技术方案
采用“四点补齐”的最小方案：

1. `PipelineConfig` 增加 `emit_debug_artifacts` 开关
2. `cli.py` 新增 `--verbose`，并改用 `logging`
3. `pipeline.py` 增加阶段日志和 debug 写出辅助函数
4. `scene_graph.py` 增加 summary 字段，`ocr.py` 增加安全 OCR 调用 warning

### 影响范围
- 修改: `src/plot2svg/config.py`
- 修改: `src/plot2svg/cli.py`
- 修改: `src/plot2svg/pipeline.py`
- 修改: `src/plot2svg/scene_graph.py`
- 修改: `src/plot2svg/ocr.py`
- 修改: `tests/test_cli.py`
- 修改: `tests/test_scene_graph.py`
- 修改: `tests/test_ocr.py`
- 修改: `tests/test_pipeline.py`

### 风险评估
- 风险 1: debug 输出开关如果默认值选错，会打破现有 pipeline 测试
- 风险 2: 在 OCR 调用层包异常时，不能误吞非 OCR 相关逻辑错误

### 关键决策
- 决策 ID: phase6-observability-1#D001
- 决策: `PipelineConfig` 默认仍保留 debug 图片输出，CLI 通过 `--verbose` 显式打开；CLI 默认关闭 debug 图片，仅保留 artifact 路径日志。
- 原因: 这样既满足 CLI 控制需求，也不破坏现有测试对 debug 文件的依赖。
