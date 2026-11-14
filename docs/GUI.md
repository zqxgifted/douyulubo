# Windows 图形界面（Tkinter 最小可用版）

[← 返回 README](../README.md) ｜ [命令对照](COMPARISON.md) ｜ [配置说明](CONFIG.md)

不想敲命令行的话，可以用仓库自带的 GUI。它**只是一个壳**：所有实际工作仍由
[`douyu.mjs`](../douyu.mjs) 与 `scripts/` 里的脚本完成，GUI 负责拼参数、起子进程、
显示实时日志。

## 启动

```bat
双击 gui\启动GUI.bat
```

或在仓库根目录执行：

```bat
python gui\app.py
```

要求：Python 3.9+（Windows 自带 tkinter）、Node.js 18+。不需要 `pip install` 任何 GUI 库。

## 界面

三个页签：

### 1. 运行 / 命令
左侧是命令列表（与 `node douyu.mjs --help` 一一对应），右侧填参数、看命令预览、执行。

| 命令 | 需要的参数 |
|---|---|
| `init` 生成配置 | 无 |
| `doctor` 环境自检 | 无（可选指定配置文件） |
| `fetch` 抓场次分段 | 配置 |
| `detail` 抓详情 | 配置 |
| `download` 批量下载 | 配置 |
| `download` 单场下载 | 配置 + `hash_id` + 输出 mp4 |
| `danmaku` 抓弹幕 | 配置 + 可选 `--limit` |
| `ass` XML→ASS | 配置 + 可选 `--limit` |
| `probe` 画质/体积核查 | 配置 + 范围（画质+体积 / 仅画质 / 仅体积） |
| `m3u8` 打印地址 | 配置 + `hash_id` |
| `stats` 码率统计 | 配置 + `--sizes` 文件 |
| `run` 一键全流程 | 配置 + 可勾选「跳过下载 / 跳过弹幕 / 跳过核查」 |
| `help` 命令帮助 | 无 |

按钮：**▶ 运行**、**■ 停止**、**清空日志**、**复制命令**。
「复制命令」会把即将执行的命令复制到剪贴板，方便你贴到终端里手动跑。

顶部还有：**打开工作目录**、**打开 config.json**、**刷新配置**。

### 2. 配置
直接编辑 `config.json` 的全部字段（[字段含义](CONFIG.md)）：

- `up_id`、`work_dir` 必填；填完点 **保存配置**
- **从示例初始化**：用 `examples/config.example.json` 生成/覆盖 config.json
- **环境自检**：直接跑 `doctor`
- `ffmpeg` / `danmaku_factory` / `work_dir` 有「浏览…」按钮
- 底部会提示 up_id 是否还是占位符、work_dir 是否为空

`config.json` 已被 `.gitignore` 排除，**不会、也不应该提交到 GitHub**。

### 3. 日志
子进程输出实时逐行显示（stdout + stderr 合并），配色区分命令 / 输出 / 错误 / 成功。

## 行为说明

- **不卡界面**：命令在后台线程里跑，日志通过队列送回主线程刷新
- **停止**：Windows 下用 `taskkill /T /F` 终止整棵进程树（`bash` 批量脚本会派生子进程，
  只杀父进程不够）；其它平台用 `terminate()`
- **不自动跑任何东西**：启动时只静默检测 `node` 是否存在，不会自动下载
- **不改核心逻辑**：GUI 只调用 `douyu.mjs`，下载/取流/弹幕代码一行没动
- **许可证清晰**：GUI 层本身是 MIT，与仓库一致；不引入任何 GPL 代码或第三方 GUI 框架

## 常见操作顺序

1. 首次使用：切到「配置」→ **从示例初始化** → 填 `up_id` 和 `work_dir` → **保存配置**
2. 点 **环境自检**（`doctor`），确认 Python / Node / ffmpeg / bash / requests 全绿
3. 回「运行」页：先 `fetch` → `detail`，看看抓到多少场/段
4. 想全量跑就点 `run`（可先勾「跳过下载」只验证数据链路）
5. 下载时可随时「停止」；日志里看进度与失败清单路径
6. 结束后用顶部按钮打开 `工作目录/downloads` 或 `data`

## 打包成 exe（可选）

```bat
pip install pyinstaller
pyinstaller --noconsole --onefile --name 斗鱼录播工具箱 gui\app.py
```

> 打包后的 exe 仍需同目录下的 `douyu.mjs`、`scripts/`、`src/`、`examples/`，
> 以及本机已安装的 Python / Node / ffmpeg。GUI 是壳，不是独立程序。

## 已知限制（最小可用版）

- 进度是纯文本日志，没有百分比进度条（脚本输出本身是行式日志）
- 没有任务队列 / 定时 / 订阅功能（刻意不做，见 [COMPARISON.md](COMPARISON.md)）
- 单场下载的 `--out` 用文件保存对话框，需自己选目录
- 没有把 `config set` 做成独立子命令；配置统一在「配置」页编辑
