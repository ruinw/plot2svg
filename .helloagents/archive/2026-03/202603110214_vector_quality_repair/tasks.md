# tasks

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 8/8 (100%) | 更新: 2026-03-11 03:20:00
当前: 已完成视觉还原修复、全量测试与样本回归，并归档方案包
<!-- LIVE_STATUS_END -->

[√] 1.1 复现 `./picture` 样本问题并确认第一轮根因 | depends_on: []
[√] 1.2 为小图坐标错位和缩放 OCR/vectorize 增加失败测试 | depends_on: [1.1]
[√] 1.3 修复路由、坐标映射和圆形注入验证 | depends_on: [1.2]
[√] 1.4 执行全量测试与样本回归，总结第一轮结果 | depends_on: [1.3]
[√] 2.1 为主样本增加“视觉还原优先”失败测试 | depends_on: [1.4]
[√] 2.2 为 scene graph 增加 region 样式抽样与透明度估计 | depends_on: [2.1]
[√] 2.3 调整 region vectorize 与 SVG 原语输出，保留填充颜色和 `fill-opacity` | depends_on: [2.2]
[√] 2.4 执行 `pytest -q` 与 `./picture` 样本视觉回归，归档结果 | depends_on: [2.3]
