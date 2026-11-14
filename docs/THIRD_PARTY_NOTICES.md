# 第三方来源与归属说明

本项目以 **MIT** 发布（见 [LICENSE](../LICENSE)）。

简要声明：

> 本产品包含对以下公开项目的参考：`renmu123/douyu-video-cli`（其
> `packages/douyu-api` 子包声明 MIT，但仓库根部为 GPL-3.0，存在声明冲突）。
> 本项目**未 vendored / import / link / 打包**任何上游源码文件，仅参考了
> 公开 API 端点、数据格式约定和通用实现思路。详见下文逐项说明。
>
> 未包含任何视频、弹幕内容、账号凭据、设备标识或平台专有代码。

---

## 1. renmu123/douyu-video-cli（douyu-api 子包）

| 项 | 内容 |
|---|---|
| 仓库 | https://github.com/renmu123/douyu-video-cli |
| 作者 | renmu123 |
| 仓库许可证 | **GPL-3.0**（仓库根 `LICENSE` 为 GPLv3 全文，README 末尾写 "GPLv3"，GitHub API 返回 `spdx_id: GPL-3.0`） |
| 子包声明 | `packages/douyu-api/package.json` 里 `"license": "MIT"` |
| 相关文件 | `packages/douyu-api/src/api/video.ts`、`src/utils.ts` |

### ⚠️ 许可证声明冲突（重要）

**同一个仓库里，根目录声明 GPL-3.0，但 `douyu-api` 子包声明 MIT。** 这是上游自身的
不一致，不是本项目的判断错误。常见解释是：作者想把可复用的 API 库单独以 MIT 发布，
但仓库根的 GPL 仍然覆盖整个工作区。两种解释的法律后果完全不同：

- 若按**仓库整体 GPL-3.0**：任何"基于该程序的修改版"整体都必须以 GPL-3.0 发布，
  与我们的 MIT 不兼容（GPL 是强 copyleft）。
- 若按**douyu-api 子包 MIT**：只需保留其版权与许可声明，MIT 与本项目 MIT 兼容。

由于我们**没有复制其源码文件**，本项目整体仍采用 MIT；但为稳妥起见：

1. 这里明确署名并链接上游，不隐瞒参考关系；
2. 在源码里对受影响的思路加了 "参考" 注释（见下）；
3. **若你打算把本项目用于商业闭源分发，建议先向上游作者确认 douyu-api 的授权范围**，
   或直接移除/重写下面列出的同源部分。

### 参考了什么（属于"读懂实现后重新写"的部分）

| 上游做法 | 本项目对应位置 | 说明 |
|---|---|---|
| `parseScript()` / `parseFunctionName()` 两段正则 | `src/douyu.mjs` 的 `extractScripts()` / `firstFunctionName()` | 正则写法相同（`/<script\b[^>]*>([\s\S]*?)<\/script>/g`、`/function\s+([a-zA-Z0-9_]+)\(/g`） |
| 取播放页**倒数第二个** `<script>` 作为签名脚本 | `src/douyu.mjs` `loadSigner()` 的 `scripts.at(-2)` | 这是上游 `parseVideo()` 的关键技巧 |
| `CryptoJS.MD5` 用 `node:crypto` 的 md5 注入后 eval 页面脚本 | `src/douyu.mjs` 顶部 `globalThis.CryptoJS` | 接口环境注入思路同源 |
| `point_id + did + 时间戳` 签名后拼 `&vid=`，POST `getStreamUrlWeb` | `src/douyu.mjs` `getTopM3u8()` | 公开接口机制，但实现顺序与上游一致 |
| 固定 DID `d6122a55e9f2d9ff39d9092800001701` | **已移除**，改为 `config.did` 留空时随机生成 | 该常量原样出现在上游 `video.ts`；本项目早期脚本也带着它，去敏时已删 |
| `getBarrageList` 分页 + B站 XML `<d p="...">` 字段顺序、8 色映射表 | `src/douyu.mjs` `fetchDanmaku()` / `toBilibiliXml()`、`scripts/step4_pull_danmaku.py` | 颜色表与 `p` 字段结构同源；上游另用 `fast-xml-parser`，本项目用字符串拼接，未用该依赖 |
| `getReplayList` / `getVideos` 的两个 wgapi 端点 | `docs/API.md`、`step1_fetch_list.py` | 公开端点 URL 与参数名 |

### 没有复制 / 没有使用什么

- 没有 vendored 任何 `.ts` 文件；没有 `import "douyu-api"`、没有依赖 `axios` /
  `safe-eval` / `fast-xml-parser`（本项目只用 Python 标准库 + `requests`、Node 原生 `fetch`）
- 没有使用其 CLI 的订阅 / webhook / 上传 B 站等功能
- 没有复制其 README 文字、代码注释或类型定义
- 本项目的分片下载（`scripts/step3_download_seg.mjs`）为独立实现：
  分片并发 + 本地拼接 + ffmpeg 转封装，不依赖 douyu-cli 或其下载器组件

### 上游版权声明（按 MIT 声明保留，供参考）

```
MIT License

Copyright (c) renmu123

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

> 上面这段是按上游 `douyu-api/package.json` 的 MIT 声明转录的**归属信息**，
> 不代表我们认定整个仓库是 MIT。仓库根 LICENSE 为 GPLv3 全文，请以
> https://github.com/renmu123/douyu-video-cli/blob/main/LICENSE 为准，
> 若有疑义请联系上游作者确认。

---

## 2. 其他公开资料 / 外部工具（非代码来源）

| 名称 | 链接 | 关系 |
|---|---|---|
| B站弹幕 XML 格式规范 | https://socialsisteryi.github.io/bilibili-API-collect/docs/danmaku/danmaku_xml.html | 公开**数据格式约定**，本项目输出遵循该格式；数据格式本身不是可版权的表达 |
| DanmakuFactory | https://github.com/hihkm/DanmakuFactory | 可选外部工具，由用户自行提供 CLI 路径，**不随本仓库分发** |
| ffmpeg | https://ffmpeg.org/ | 可选外部工具，由系统 PATH 提供，**不随本仓库分发** |

---

## 3. 本项目的立场

- 本仓库整体以 **MIT**（[LICENSE](../LICENSE)）发布
- 未包含任何上游项目的源码文件、二进制、视频、弹幕内容或凭据
- 保留上述署名，是为了尊重"参考了别人的实现"这一事实，也是 MIT/BSD 类许可证的通行做法
- **上游许可证冲突尚未由上游作者澄清**。若你需要把本项目用于商业闭源产品，
  建议：① 向上游确认 douyu-api 的授权范围；或 ② 将第 1 节列出的同源部分
  （签名提取正则、`scripts.at(-2)`、颜色映射表）按公开接口文档独立重写后移除署名依赖
