# scripts/

各步骤的实际执行脚本。GUI 和 CLI 都调用这里的文件。

## 抓取

| 文件 | 说明 |
|---|---|
| `list_shows.py` | 录播列表：场次 → 分段两级展开，可选补 `point_id` |
| `list_posts.py` | 投稿列表（`author-video`） |
| `step1_fetch_list.py` | 仅抓场次索引（快） |
| `step2_fetch_detail.py` | 抓每个场次的分段详情 |
| `probe_page.mjs` | 探测指定场次的清晰度、大小、精确开播时间 |
| `probe_segments.mjs` | 批量探测分段元数据 |
| `probe_meta_fast.py` | 轻量版元数据探测 |

## 下载

| 文件 | 说明 |
|---|---|
| `step3_download_seg.mjs` | 单段下载：m3u8 分片并发 + 拼接，支持断点续传 |
| `step3_download_batch.mjs` | 批量下载，N 个任务并发 |
| `lib_get_m3u8.js` | m3u8 解析辅助 |

## 转码

| 文件 | 说明 |
|---|---|
| `merge_ts.py` | **从 ts 分片直接合并转码**（不产生中间文件） |
| `transcode_video.py` | 转码已有视频文件 |
| `transcode_av1.py` | 早期的 AV1 专用脚本（保留兼容） |

## 弹幕

| 文件 | 说明 |
|---|---|
| `step4_pull_danmaku.py` | 抓取弹幕 XML |
| `util_convert_danmaku_ass.py` | XML → ASS 转换入口 |

## 工具

| 文件 | 说明 |
|---|---|
| `util_bitrate_stats.py` | 码率统计 |
| `step5_probe_quality_all.js` | 全量清晰度探测 |
| `step5_probe_size_all.js` | 全量体积探测 |
