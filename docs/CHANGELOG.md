# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.0.1] - 2026-11-15

首个公开版本。从一次真实的大批量录播归档实践中提炼出通用工具，并做了完整去敏：

- 移除全部真实主播 ID、昵称、房间号、设备号、本机绝对路径、会话转录路径与网盘私有目录
- 重写为统一配置（`src/config.py` / `src/config.mjs`），`up_id` / `work_dir` 改为必填
- 修复原模板中 `step1` 的配置加载 NameError
- 修复固定「文件过小」阈值误杀超短场次的问题
- 弹幕抓取改为读 `download_list.json`，不再依赖任何会话记录或网盘快照
- 码率统计改为读取显式传入的 `--sizes` 清单
- 新增 MIT LICENSE、README、配置 / 接口 / 避坑文档、Issue / PR 模板、行为准则、
  安全政策、`.gitignore` 与全源码 SPDX 标识
- 新增 `NOTICE` 与 `THIRD_PARTY_NOTICES.md`：记录对
  renmu123/douyu-video-cli（douyu-api）的参考与归属，
  并标注上游仓库 GPL-3.0 与子包 MIT 声明冲突
- 新增统一命令入口 `douyu.mjs`（`init` / `fetch` / `detail` / `download` / `danmaku` /
  `ass` / `probe` / `m3u8` / `stats` / `run` / `doctor`）
- 新增与上游项目的功能对比文档 `docs/COMPARISON.md`
- 新增 Windows 图形界面 `gui/app.py`（Tkinter）：覆盖全部 CLI 命令、配置编辑、
  实时日志、停止进程树、打开工作目录；配套 `gui/启动GUI.bat` 与 `docs/GUI.md`
- 新增**内置纯 Python 弹幕转 ASS**（`src/danmaku_ass.py`），不再需要外部 DanmakuFactory；
  滚动弹幕做逐轨道几何碰撞检测（只比较屏幕可见区域），实测各类密度下视觉重叠为 0，
  超容量时自动降级为顶部固定弹幕，见 `docs/DANMAKU.md`
- 新增**下载历史**（`src/history.py` / `src/history.mjs`，每场一个 JSON）与
  `history` 命令、GUI「下载管理 / 历史」页；同一个录播重复下载会提示「已下载」
- 新增**清晰度选择**（`quality`，默认 `highest`）与弹幕模式（`danmaku_mode`：
  `ass`/`xml`/`none`，默认 `ass`）；GUI 提供两个下拉框
- 新增 `scripts/step3_download_batch.mjs`（Node 版批量调度，去除 bash 依赖）
- 新增自包含发布包构建（`build_release.ps1` + `build_exe.spec`）：exe 内含 Python 解释器
  与 requests，并把 node.exe / ffmpeg.exe 一并打包，实现解压即用
