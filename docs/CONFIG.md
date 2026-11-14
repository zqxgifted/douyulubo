# 配置说明

[← 返回 README](../README.md)

所有脚本共用一份配置，读取优先级（高 → 低）：

1. 环境变量 `DOUYU_CONFIG` 指向的 JSON 文件
2. 当前工作目录下的 `config.json`
3. `DOUYU_*` 环境变量
4. 内置默认值

`config.json` 已被 `.gitignore` 排除，**不要提交真实配置**。

## 配置项

| 键 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `up_id` | ✅ | — | 主播录播页 `https://v.douyu.com/author/<up_id>` 里那段 ID |
| `work_dir` | ✅ | — | 工作目录；所有产物都在它下面 |
| `concurrent` | | `2` | 批量下载的对外并发数 |
| `ffmpeg` | | `ffmpeg` | ffmpeg 可执行文件；用 PATH 名即可，别写死绝对路径 |
| `danmaku_factory` | | 空 | DanmakuFactory CLI 路径；只有 XML→ASS 时才需要 |
| `ua` | | 常见 Chrome UA | 请求 User-Agent |
| `did` | | 空 → 随机生成 | 设备 ID，32 位 hex；留空时每次随机生成，也可固定 |
| `workers_per_task` | | `8` | 单个下载任务内的分片并发 worker 数 |
| `min_file_mb` | | `100` | 输出小于该值视为失败；短场次可设 `0` 关闭 |
| `anchor_name` | | 空 | 只写进弹幕 XML 的 `user_name` 元数据，可留空 |

### 环境变量对应关系

| 变量 | 覆盖的键 |
|---|---|
| `DOUYU_CONFIG` | 配置文件路径 |
| `DOUYU_UP_ID` | `up_id` |
| `DOUYU_WORK_DIR` | `work_dir` |
| `DOUYU_FFMPEG` | `ffmpeg` |
| `DOUYU_DANMAKU_FACTORY` | `danmaku_factory` |
| `DOUYU_UA` | `ua` |
| `DOUYU_DID` | `did` |
| `DOUYU_CONCURRENT` | `concurrent` |
| `DOUYU_WORKERS_PER_TASK` | `workers_per_task` |
| `DOUYU_MIN_FILE_MB` | `min_file_mb` |
| `DOUYU_ANCHOR_NAME` | `anchor_name` |

`up_id` / `work_dir` 缺失时会直接报错退出，**不会回落到任何真实主播**。
`did` 留空即随机生成，避免把设备号写进仓库；若需跨次保持一致，自行在本机配置里固定。

## 目录约定

```
<work_dir>/
├── data/            raw_shows.json / raw_segments.json / raw_detail.json
│                    download_list.json / probe_input.json
│                    size_results.json / quality_results.json / bitrate.json
├── downloads/       <场次名>.mp4 + <场次名>-ts/（分片临时目录）
├── danmaku/         <YYYYMM>/<场次名>.xml
├── danmaku_ass/     <YYYYMM>/<场次名>.ass
└── tmp/             TMP / TEMP 指向这里
```

> 目录名用英文，避免 Windows 下中文路径与编码带来的问题；文件名（场次名）保留斗鱼官方
> `title`，以便和视频一一对应。

## 最小配置示例

```json
{
  "up_id": "<你的主播 ID>",
  "work_dir": "./workspace"
}
```

其余项用默认值即可。完整示例见 [examples/config.example.json](../examples/config.example.json)。
