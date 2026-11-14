# core/

命令行入口与依赖声明。

| 文件 | 说明 |
|---|---|
| `douyu.mjs` | CLI 主入口，`node core/douyu.mjs --help` 查看全部命令 |
| `package.json` | Node 侧元数据（无第三方依赖，仅用原生模块） |
| `requirements.txt` | Python 侧依赖（仅 `requests`） |

GUI 会调用这里的 `douyu.mjs`；也可以脱离 GUI 单独在终端使用。
