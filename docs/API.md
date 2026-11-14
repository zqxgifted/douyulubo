# 斗鱼录播接口速查

[← 返回 README](../README.md)

> 均为 `v.douyu.com` 的公开 wgapi，无需登录态，只需正常 User-Agent。
> 接口可能变更，脚本内不要缓存签名函数。以下为字段与机制的说明，不含任何真实 ID。

## 1. 主播的全部场次

```
GET https://v.douyu.com/wgapi/vod/center/authorShowVideoList
    ?up_id=<UP_ID>&page=<n>&limit=50
```

```json
{
  "data": {
    "count": 878,
    "list": [
      { "show_id": "...", "title": "...",
        "video_list": [{ "hash_id": "...", "video_url": "..." }] }
    ]
  }
}
```

- `count` 是总场次数，用来判断是否拉全
- `video_list[0].hash_id` 是后续要用的段 ID

## 2. 某个场次的分段（多段连播）

```
GET https://v.douyu.com/wgapi/vod/center/getShowReplayList
    ?vid=<hash_id>&up_id=<UP_ID>
```

返回 `data.list[]`，每项一个分段（含自己的 `hash_id` / 时长 / 弹幕数）。
**分段才是视频单元**；一个 show 可能有多个分段。

## 3. 取播放地址（需要签名）

**第一步：从播放页提取签名函数**

```
GET https://v.douyu.com/show/<hash_id>
```

页面里有多个 `<script>`，倒数第二个包含生成签名的函数（形如 `function _xxxx(...)`）。
`eval` 之后调用：

```js
const body = `${signFn(point_id, DID, Math.floor(Date.now()/1000))}&vid=${hash}`;
```

> 签名函数会轮换，必须**每次实时从页面抓**，不能硬编码；本项目在
> [`src/douyu.mjs`](../src/douyu.mjs) 的 `loadSigner()` 里实现。

**第二步：POST 取流**

```
POST https://v.douyu.com/wgapi/vodnc/front/stream/getStreamUrlWeb
Content-Type: application/x-www-form-urlencoded

<body>
```

```json
{
  "error": 0,
  "data": {
    "thumb_video": {
      "原画":  { "name": "原画", "bit_rate": 2000, "url": "https://.../xxx.m3u8" },
      "高清":  { "name": "高清", "bit_rate": 1500, "url": "..." },
      "标清":  { "name": "标清", "bit_rate": 800,  "url": "..." }
    }
  }
}
```

按 `bit_rate` 降序取第一个 = 最高画质。若拿到的是 master playlist
（含 `#EXT-X-STREAM-INF`），需再取一层 media playlist。

## 4. 弹幕

```
GET https://v.douyu.com/wgapi/vod/center/getBarrageList
    ?vid=<hash_id>&start_time=<ms>&end_time=<ms>
```

- 分页拉取：每窗口上限 500 条，用已返回弹幕的最大 `tl` + 1 作为下一窗口起点
- `point_id` 是**分段**级的，不是场次级；同一场次的不同分段要分别拉
- 斗鱼返回内容随观看累积，同一个 VOD 不同时间拉，弹幕条数会不同
- 本项目按 `(uid, sts, ctt)` 去重后输出 B 站格式 XML

## 5. 官方元数据字段

播放页 HTML 里可提取（见 `step2_fetch_detail.py`）：

| 字段 | 含义 | 可信度 |
|---|---|---|
| `duration_sec` | 官方时长（秒） | **权威**，用于校验下载完整性 |
| `official_bit_rate` | 标称码率（kbps） | 档位值，非实际平均码率 |
| `danmu_num` | 弹幕条数 | 参考 |
| `start_time` | 开播时间戳 | 判断场次归属（注意时区 +8） |
| `point_id` | 取流 / 弹幕 ID | **必需**，务必保存 |

`est_size = 标称码率 × 时长 ÷ 8` 是推算值，实测误差 ±5~10%（普遍低估约 3%），
**只能当下限参照**。

## 6. 已知异常

| 现象 | 说明 |
|---|---|
| 现行 m3u8 比原始短 | 老 VOD 可能被平台裁剪；旧文件反而是完整母版 |
| 同一 show 拆多段 | 连播会拆成多个独立段 |
| 标签笔误 | 官方 `title` 里的日期可能与场次实际不符，以官方记录为准 |
| 签名轮换 | 取流失败 `error=7` 之类，重载页面签名函数再试 |
