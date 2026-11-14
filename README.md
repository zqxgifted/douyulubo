# douyulubo · 斗鱼录播下载与归档

**版本 v0.0.1**

把斗鱼（v.douyu.com）主播的历史录播批量下载到本地，可选直接转码为 H.264 / H.265 / AV1。

**图形界面，不用敲命令。**

---

## 快速开始

### 方式一：用打包好的（推荐）

从 [Releases](../../releases) 下载，二选一：

| | 完整包 | 代码包 |
|---|---|---|
| 文件名 | `douyulubo_vX.Y.Z_win-x64.zip` | `douyulubo_vX.Y.Z_win-x64-lite.zip` |
| 体积 | 约 98 MB | 约 18 MB |
| 依赖 | 已内置 node + ffmpeg | 需自备 Node.js 18+ 与 ffmpeg |

解压后双击 **douyulubo.exe**：

1. 首次启动会提示填写主播 ID，或直接点「搜索」粘贴主播链接
2. 勾选要下载的场次（可按时段、关键词筛选）
3. 点「下载选中」

### 方式二：从源码运行

```bash
pip install -r core/requirements.txt   # 仅需 requests
python gui/app.py
```

需要 Python 3.9+（含 tkinter）、Node.js 18+、ffmpeg。

### 方式三：自行打包

```powershell
powershell -ExecutionPolicy Bypass -File ..\build_release.ps1
```

产物为两个 zip：完整包与代码包。

---

## 配置

所有配置在 `config/` 目录：

| 文件 | 说明 |
|---|---|
| `config/defaults.json` | 通用默认值（已随仓库提供） |
| `config/user.example.json` | 用户配置模板 |
| `config/user.json` | **你的配置**（`up_id`、工作目录等，不随仓库分发） |

快速配置：

```powershell
Copy-Item config\user.example.json config\user.json
# 编辑 config/user.json，填入 up_id
```

`up_id` 即录播页地址末尾那段：
`https://v.douyu.com/author-replay/<这段就是 up_id>`

配置项说明见 [config/README.md](config/README.md)。

---

## 界面

| 页签 | 作用 |
|---|---|
| **搜索** | 粘贴主播链接 → 搜索 → 勾选场次 → 下载 |
| **下载管理** | 下载历史、进度与速度、打开下载目录 |
| **配置** | 组件路径、下载设置、转码设置、弹幕参数、日志 |

---

## 命令行

```bash
node core/douyu.mjs --help     # 全部命令
node core/douyu.mjs doctor     # 检查环境
```

---

## 转码（可选）

下载完成后可直接转码为更小的格式，在「配置 → 转码」里开启：

| 编码 | 适用显卡 | 说明 |
|---|---|---|
| H.265 | GTX 16 / RTX 20·30 系 | 默认，兼容性最好 |
| AV1 | RTX 40 系及以上 | 压缩率最高 |
| H.264 | 任意 | 兼容性最广 |

直接从 ts 分片合并转码，不产生中间文件。支持文件名后缀（如 `xxx_AV1.mp4`）。

---

## 目录结构

```
├── config/       配置（defaults.json 通用 / user.json 私有）
├── core/         命令行入口 douyu.mjs
├── gui/          tkinter 图形界面
├── scripts/      抓取、下载、转码、弹幕各步骤脚本
├── src/          共用的核心模块
├── docs/         详细文档
└── examples/     配置示例
```

---

## 文档

| 文档 | 内容 |
|---|---|
| [config/README.md](config/README.md) | 全部配置项说明 |
| [scripts/README.md](scripts/README.md) | 各脚本用途一览 |
| [docs/README.md](docs/README.md) | 详细文档索引 |
| [docs/API.md](docs/API.md) | 使用的斗鱼公开接口 |
| [docs/CONFIG.md](docs/CONFIG.md) | 配置优先级与进阶用法 |
| [docs/DANMAKU.md](docs/DANMAKU.md) | 弹幕与 ASS 字幕 |
| [docs/GUI.md](docs/GUI.md) | 界面操作说明 |
| [docs/PITFALLS.md](docs/PITFALLS.md) | 常见问题 |
| [docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md) | 第三方来源与归属 |

---

## 参考资料

- [renmu123/douyu-video-cli](https://github.com/renmu123/douyu-video-cli) — 斗鱼视频 API 与签名机制的参考实现
- [B站弹幕 XML 格式规范](https://socialsisteryi.github.io/bilibili-API-collect/docs/danmaku/danmaku_xml.html) — 弹幕 XML 输出格式依据
- [DanmakuFactory](https://github.com/hihkm/DanmakuFactory) — 可选的 XML → ASS 转换工具

---

## 许可

MIT，见 [LICENSE](LICENSE)。

本项目不包含任何视频、弹幕内容或账号凭据。下载的内容版权归原作者与平台所有，
请仅用于个人归档，遵守平台服务条款与当地法律。
