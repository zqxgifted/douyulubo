# 与 renmu123/douyu-video-cli 的对比

[← 返回 README](../README.md) ｜ [归属说明](../THIRD_PARTY_NOTICES.md)

> 对比基准：上游 [douyu-video-cli](https://github.com/renmu123/douyu-video-cli) 仓库
> `main` 分支（README、`packages/douyu-api`、`douyu-cli` CLI 说明，2026-11-12 查阅）。
> 本项目参考了它的公开接口与弹幕格式约定，但定位不同：**上游是「下载单个/订阅主播的 CLI 工具」，
> 本项目是「把某主播全部历史录播完整归档 + 核查」的工具箱**。

## 一、定位差异（一句话）

| | 上游 douyu-video-cli | 本项目 |
|---|---|---|
| 目标 | 给定 URL 下载某场录播；订阅主播自动下最新回放 | 把**一个主播的全部历史场次/分段**抓全、下全、核查、归档 |
| 单位 | URL / show | **分段（segment）**才是视频单元 |
| 输出 | ts（默认）/ 可选 mp4、弹幕 XML | mp4 + XML + 可选 ASS，按月份目录 |
| 使用者 | 终端用户，装了就能用 | 需要自己填配置、可逐脚本审计/改写的工具箱 |

## 二、功能对照

| 能力 | 上游 | 本项目 | 说明 |
|---|---|---|---|
| 下载单场录播 | ✅ `douyu download <url>` | ✅ `node douyu.mjs download --hash <id> --out <file>` | 都支持 |
| 下载全部分 p | ✅ `-a` | ✅ step1 自动展开全部分段 | 本项目按 `video_list[0].hash_id` → `getShowReplayList` 全量扁平化 |
| 指定清晰度 | ✅ `-st` | ✅ 固定取 `bit_rate` 最高档 | 上游可选档位；本项目只保留最高画质，因为目标是"完整母版" |
| 弹幕下载 | ✅ `-d`，B站 XML | ✅ step4，B站 XML | 格式约定相同 |
| 弹幕并发 | — | ✅ step4 可配、`pull` 版曾 4 并发 | 本项目大批量场景优化 |
| XML → ASS | 依赖外部 DanmakuFactory（README 建议） | ✅ `ass` 命令封装，路径可配 | 都依赖同一外部工具，本项目把它参数化 |
| ffmpeg 转封装 | ✅ 需 `--ffpath` / `config set` | ✅ `ffmpeg` 配置项 + 自动 `-c copy -bsf:a aac_adtstoasc` | 都可调路径 |
| 分片并发 / 断点续跑 | ✅ `-conc`、`-si/-ei` | ✅ 8 worker + 分片 >10KB 跳过 + 二进制拼接 | 思路类似，本项目加"拼接大小校验才重建" |
| 订阅 / 定时 / webhook | ✅ `sub add` / `sub server` / `--webhook` | ❌ 不做 | **刻意不做**：归档是一次性全量任务，不是持续订阅 |
| 上传 B 站 / 对接 biliLive-tools | ✅ 联动 | ❌ 不做 | 本项目不涉及任何第三方平台写入 |
| **全量场次枚举** | ⚠️ 按 URL/订阅，不做全量基准清单 | ✅ `raw_shows.json` + `raw_segments.json` + `download_list.json` | 本项目的核心：先有权威基准清单，再逐项核对 |
| **官方时长校验** | — | ✅ `ffprobe` 时长 vs `duration_sec`（±3%） | 防止"下到了但被截短" |
| **画质/体积核查** | — | ✅ `probe quality` / `probe size` 两脚本 | 判断已有文件是不是最高档、足不足料 |
| **码率统计 / 分档** | — | ✅ `stats` 命令 | 用大小÷时长分 480p/720p 档 |
| **est_size 误差模型** | — | ✅ 文档化 ±5~10%、平均低估 3% | 避免用 ±1MB 误判 |
| **磁盘空间守门** | — | ✅ 批量脚本剩余 <10GB 自动中止 | 大批量下载防占满盘 |
| **临时文件不写系统盘** | — | ✅ `TMP/TEMP` 指向 `<work_dir>/tmp` | 大批量场景实测需要 |
| **失败清单 / 进度文件** | 部分 | ✅ `_failed.txt`、`_progress.json` | 可续跑、可审计 |
| **配置去敏** | DID 硬编码在源码里 | ✅ `did` 留空即随机生成；`up_id`/`work_dir` 必填 | 见下 |
| **全部参数统一入口** | 分散在 CLI 参数与 `config set` | ✅ `src/config.py` + `src/config.mjs` 单一来源 | 环境变量 > 配置文件 > 默认值 |
| 语言 / 依赖 | TypeScript, Node>=20, axios/safe-eval/fast-xml-parser | Python 3.9+ (requests) + Node 18+ (原生 fetch) | 本项目依赖更少、门槛更低 |
| 许可证 | 仓库 GPL-3.0（子包声明 MIT，冲突） | 本项目 MIT + 完整归属 | 见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) |

## 三、改进了哪些方面（相对上游）

### 1. 从「下载一个视频」升级到「完整归档一个主播」
- 上游以 URL 或"最近一次回放"为输入；本项目 step1 先把 `authorShowVideoList` 翻到空页、
  再对**每个 show** 调 `getShowReplayList`，产出分段级别的基准清单。
- 有了基准清单才能回答"到底齐没齐"——这是归档和单纯下载的根本区别。

### 2. 把"踩过的坑"写进代码和文档，而不是留在会话里
| 坑 | 本项目的处理 |
|---|---|
| 老 VOD 现行 m3u8 比原始短 | 文档明确"重下载只补缺，不要替换旧母版"，校验用 `ffprobe` 时长而非文件大小 |
| 固定 50MB "文件过小"阈值误杀短场次 | 改为可配 `min_file_mb`，且对 <15 分钟的官方短段豁免 |
| 签名函数轮换 | `loadSigner()` 每次实时抓页面脚本；`probe` 脚本内置 `error=7` 重载一次 |
| master playlist | `parsePlaylist()` 显式抛错提示再取一层 |
| 跨场次内容重复 | 验收清单要求用本地真 md5 比对，不用搜索接口的假 md5 |

### 3. 去敏与可移植
- 上游 `video.ts` 里硬编码了 DID `d6122a55...` 和固定 UA；本项目 `did` 留空随机生成，
  `up_id`/`work_dir` 必填且缺失即报错，不回落任何真实主播。
- 目录名改为英文（`data/downloads/danmaku/...`），避免中文路径与编码问题；
  早期版本里的 `D:\Library\...`、会话 JSONL、网盘私有路径全部移除。

### 4. 运维友好
- 统一命令入口 `node douyu.mjs <command>`（见下节），`doctor` 一键体检。
- 断点续跑贯穿下载、弹幕、探测；失败清单单独落盘。
- 并发与磁盘守门：对外默认 2 并发、单任务内 8 worker、空间 <10GB 中止。

### 5. 文档与合规
- 配置 / 接口 / 避坑 / 验收四份文档 + MIT LICENSE + NOTICE + 第三方归属 + 社区标准文件齐全。
- 上游的许可证冲突被明确记录，而不是默默忽略。

## 四、"上游有各种命令，我这个行不行"

**行，而且已经做了。** 统一入口是 [douyu.mjs](../douyu.mjs)：

```bash
node douyu.mjs --help          # 列出全部命令
node douyu.mjs init            # 生成 config.json
node douyu.mjs doctor          # 体检 Python/Node/ffmpeg/配置
node douyu.mjs run             # 一键跑完整流程
node douyu.mjs fetch           # 抓场次与分段
node douyu.mjs detail          # 抓详情 + 生成下载清单
node douyu.mjs download        # 批量下载
node douyu.mjs danmaku         # 抓弹幕
node douyu.mjs ass             # XML -> ASS
node douyu.mjs probe           # 核查画质/体积
node douyu.mjs m3u8 <hash>     # 打印某场 m3u8
node douyu.mjs stats --sizes f # 码率统计
```

对照上游的 `douyu download / sub add / sub server / config set / help`：

- **覆盖**：`download`、`--help`、`config`（本项目用 `init` + `doctor` + 配置文件）
- **额外有**：`fetch / detail / danmaku / ass / probe / stats / m3u8 / run / doctor`
- **没有**：`sub`（订阅）、`server`（定时）、`webhook`、上传 B 站 —— 这些是"持续追更/联动"，
  与"一次性全量归档"目标不同，刻意不做，也不写进代码。

`run` 还支持 `--skip-download` / `--skip-danmaku` / `--skip-probe`，可以只跑数据抓取先看看清单。
所有命令都能用 `--config <file>` 指定配置，等价于 `DOUYU_CONFIG`。

## 五、还有什么可以再进一步

按投入从低到高：

| 方向 | 说明 | 工作量 |
|---|---|---|
| `config` 子命令 | 像上游 `config set` 那样读写 config.json（当前是手改文件） | 小 |
| 断点/重试可视化 | 输出更细的进度与 ETA、失败自动重试 N 次 | 小 |
| `verify` 命令 | 把 PITFALLS 的验收清单自动化（ffprobe 时长比对、md5 查重、XML/ASS 配对） | 中 |
| 归档打包 / 目录规范 | 自动按 `<YYYYMM>/` 整理视频+XML+ASS 三件套并校验命名一致 | 中 |
| 并发/限流自适应 | 根据失败率动态调整并发，避免触发平台限流 | 中 |
| **Windows GUI** | ✅ 已实现最小可用版，见 [GUI.md](GUI.md) 与下节 | 已完成 |
| 跨平台 CI / 单元测试 | 用 mock 的 HTTP 响应测脚本，避免每次真连斗鱼 | 中 |

## 六、Windows 窗口程序（不用命令行）

**已经做了最小可用版**：[gui/app.py](../gui/app.py)（Tkinter），双击
[gui/启动GUI.bat](../gui/启动GUI.bat) 即可。使用说明见 [GUI.md](GUI.md)。
下面保留当时的设计与路线说明，便于理解为什么这么做。

但要分清三层，别混：

```
GUI (Win)  ──调用──>  douyu.mjs / scripts  ──读──> config.json
   ↑ 只负责：选主播ID、选目录、点按钮、显示进度/日志
   ↑ 不需要改任何下载逻辑
```

### 为什么适合
- 所有脚本已经**全部参数化**（config.json / 环境变量），没有硬编码路径
- 已有统一命令入口 `douyu.mjs`，GUI 只要 `spawn` 它并解析 stdout
- Python/Node 子进程输出是行式日志，GUI 直接逐行显示即可
- `doctor` 命令可以直接做成 GUI 的"环境自检"页

### 三种实现路线（按推荐度）

| 方案 | 技术 | 优点 | 代价 |
|---|---|---|---|
| **A. 本地 Web UI（推荐先做）** | 一个 Node/Python 小服务 + 浏览器页面（或 Electron/Tauri 壳） | 复用现有脚本零改动；界面用 HTML 好做；还能远程看进度 | 要跑一个本地端口 |
| **B. Python Tkinter / PyQt** | 直接 `subprocess` 调脚本，QTextEdit 显示日志 | 单文件、免浏览器、打包成 exe 简单（PyInstaller） | 界面朴素；要处理中文路径 |
| **C. .NET WinForms/WPF** | C# 调 Python/Node 子进程 | 原生 Windows 观感、可做安装包 | 多一门语言，与现有栈不一致 |

> 注意：**不要把 GPL 项目或任何第三方 GUI 框架代码混进来**，GUI 层单独用 MIT 写，
> 通过进程调用本仓库脚本即可保持许可证清晰。

### 已实现的 GUI 功能（方案 B：Python Tkinter）
1. ✅ 配置页：`up_id`、`work_dir`、ffmpeg/DanmakuFactory 路径、`did` 等全部字段，可保存 / 重载 / 从示例初始化
2. ✅ 环境自检：`doctor` 结果直接显示在日志区
3. ✅ 一键流程页：`run` + 实时日志 + 可勾选跳过项
4. ✅ 全部命令页：`init / doctor / fetch / detail / download(批量/单场) / danmaku / ass / probe / m3u8 / stats / run / help`，含参数输入与命令预览
5. ✅ 打开工作目录 / 打开 config.json / 复制命令 / 停止进程树
6. ✅ 安全：GUI 不保存任何真实凭据到仓库；配置写本地 `config.json`（已被 .gitignore 排除）
7. ⚠️ 未做：百分比进度条（脚本输出是行式日志，GUI 逐行显示）、任务队列、订阅定时

**结论**：命令行入口与 GUI 都齐了；GUI 是"再加一层壳"，不动核心逻辑。
若要进一步，可走方案 A 做本地 Web UI 以便远程查看进度，或用 PyInstaller 打包成 exe。

---

> 本文档仅作功能对比，不构成对上游项目的评价或法律意见。上游许可证状态见
> [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
