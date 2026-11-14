# douyulubo · 斗鱼录播下载与归档

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

## 文档

| 文档 | 内容 |
|---|---|
| [config/README.md](config/README.md) | 全部配置项说明 |
| [docs/API.md](docs/API.md) | 使用的斗鱼公开接口 |
| [docs/CONFIG.md](docs/CONFIG.md) | 配置优先级与进阶用法 |
| [docs/DANMAKU.md](docs/DANMAKU.md) | 弹幕与 ASS 字幕 |
| [docs/GUI.md](docs/GUI.md) | 界面操作说明 |
| [docs/PITFALLS.md](docs/PITFALLS.md) | 常见问题 |
| [THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md) | 第三方来源与归属 |

---

## 参考资料

本项目在实现过程中参考了以下公开项目与文档。**未复制任何上游源码文件**，
保留归属是为了尊重「参考了别人的实现」这一事实。

### renmu123/douyu-video-cli

- 仓库：<https://github.com/renmu123/douyu-video-cli>
- 作者：renmu123
- 许可证：仓库根为 **GPL-3.0**；其 `packages/douyu-api/package.json` 声明 **MIT**（上游自身声明冲突）

参考内容：

| 参考点 | 本项目位置 |
|---|---|
| 播放页签名脚本提取（取倒数第二个 `<script>`、正则写法） | `src/douyu.mjs` |
| `CryptoJS.MD5` 用 `node:crypto` 注入后执行页面脚本 | `src/douyu.mjs` |
| `point_id + did + 时间戳` 签名机制 | `src/douyu.mjs` |
| 斗鱼 wgapi 公开端点与参数 | `docs/API.md`、`scripts/` |
| 弹幕 `getBarrageList` 分页与 B站 XML 字段结构 | `src/douyu.mjs`、`scripts/step4_pull_danmaku.py` |

**没有做**：未 vendored 任何 `.ts` 文件，未 `import` 该包，未依赖其 `axios` /
`safe-eval` / `fast-xml-parser`，未使用其 CLI 的订阅、上传等功能。

> ⚠️ 上游许可证声明存在冲突（仓库 GPL-3.0 vs 子包 MIT）。

### 其它公开资料

| 名称 | 链接 | 关系 |
|---|---|---|
| B站弹幕 XML 格式 | [规范文档](https://socialsisteryi.github.io/bilibili-API-collect/docs/danmaku/danmaku_xml.html) | 遵循该公开数据格式 |
| DanmakuFactory | [hihkm/DanmakuFactory](https://github.com/hihkm/DanmakuFactory) | 可选外部工具，不随本项目分发 |
| ffmpeg | [ffmpeg.org](https://ffmpeg.org/) | 可选外部工具，不随本仓库分发 |

详细的逐项说明（含上游 MIT 声明全文、冲突分析）见
[docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md)。

---

## 许可

MIT，见 [LICENSE](LICENSE)。

本项目不包含任何视频、弹幕内容或账号凭据。下载的内容版权归原作者与平台所有，
请仅用于个人归档，遵守平台服务条款与当地法律。
