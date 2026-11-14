# src/

GUI 与 CLI 共用的核心模块。

| 文件 | 说明 |
|---|---|
| `config.py` / `config.mjs` | 配置加载（分层合并：defaults → user → 环境变量） |
| `douyu.mjs` | 斗鱼接口封装：签名提取、取流、m3u8 解析、弹幕抓取 |
| `danmaku_ass.py` | 纯 Python 实现 XML → ASS，含防重叠排版算法 |
| `history.py` / `history.mjs` | 下载历史读写（每条记录一个 JSON） |
| `anchor.py` | 主播信息（昵称等）获取 |

`config.py` 与 `config.mjs` 逻辑保持一致：Python 侧脚本和 Node 侧脚本读到的配置相同。
