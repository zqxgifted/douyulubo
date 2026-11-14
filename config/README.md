# 配置说明

本目录存放全部配置文件。**核心原则：敏感信息与通用默认值分开存放**，
这样上传到 GitHub 时不会误带个人数据。

## 文件清单

| 文件 | 是否提交 | 用途 |
|---|---|---|
| `defaults.json` | ✅ **提交** | 通用默认值，不含任何个人数据 |
| `user.example.json` | ✅ **提交** | 用户配置模板（只有占位符） |
| `user.json` | ❌ **不提交** | 你的真实配置（up_id、本机路径等） |

## 快速开始

1. 把 `user.example.json` 复制为 `user.json`：

   ```powershell
   Copy-Item config\user.example.json config\user.json
   ```

2. 编辑 `user.json`，填入你的 `up_id`：

   ```json
   {
     "up_id": "<你的up_id>"
   }
   ```

   `up_id` 就是录播页地址末尾那段：
   `https://v.douyu.com/author-replay/<你的up_id>`

3. 启动 `douyulubo.exe` 即可。

## 配置优先级

从低到高，后面的覆盖前面的：

```
内置默认值
  ↓
config/defaults.json      通用默认（仓库里）
  ↓
config/user.json          你的配置（不提交）
  ↓
DOUYU_CONFIG 指定的文件     临时覆盖
  ↓
环境变量 DOUYU_*           最高
```

## 常用配置项

### 基础

| 键 | 说明 | 默认 |
|---|---|---|
| `up_id` | 主播 ID（必填） | — |
| `work_dir` | 下载根目录，留空 = 程序目录下 `downloads` | `""` |
| `concurrent` | 同时下载几个分段 | `2` |
| `min_file_mb` | 小于这个大小视为下载失败 | `100` |

### 转码

| 键 | 说明 | 默认 |
|---|---|---|
| `transcode_enabled` | 下载后自动转码 | `false` |
| `transcode_codec` | `h265` / `av1` / `h264` | `h265` |
| `transcode_quality` | `high` / `balanced` / `small` / `tiny` | `balanced` |
| `transcode_suffix` | 文件名后缀，如 `AV1` → `xxx_AV1.mp4` | `""` |
| `transcode_delete_src` | 转码后删原片 | `false` |
| `transcode_merge_ts` | 直接从 ts 分片合并转码（不产生中间文件） | `true` |

**编码器建议**

| 显卡 | 推荐 codec | 说明 |
|---|---|---|
| RTX 40 系 | `av1` | 压缩率最高，硬件编码 |
| GTX 16 / RTX 20·30 | `h265` | 性价比最好 |
| 其他 / 集显 | `h264` | 兼容性最好 |

> 开源版默认 `h265`，因为兼容性最广。AV1 需要 RTX 40 系以上。

### 弹幕

| 键 | 说明 | 默认 |
|---|---|---|
| `danmaku_mode` | `ass` / `xml` / `none` | `ass` |
| `font_name` | 字体 | `微软雅黑` |
| `font_size` | 字号 | `50` |
| `scroll_duration` | 滚动弹幕飞行秒数 | `8.0` |
| `fixed_duration` | 固定弹幕停留秒数 | `4.5` |
| `opacity` | 不透明度 0-255 | `255` |

## 上传 GitHub 前的检查

```powershell
# 确认 user.json 不会被提交
git check-ignore config/user.json
# 有输出 = 被忽略（正确）

# 预览将要提交的文件
git add -An .
```

如果 `config/user.json` 出现在 `git add -An` 的输出里，说明 `.gitignore` 有问题，**先修好再提交**。

## 环境变量

不写配置文件也可以，用环境变量：

| 变量 | 对应配置 |
|---|---|
| `DOUYU_UP_ID` | `up_id` |
| `DOUYU_WORK_DIR` | `work_dir` |
| `DOUYU_CONCURRENT` | `concurrent` |
| `DOUYU_TRANSCODE_CODEC` | `transcode_codec` |
| `DOUYU_TRANSCODE_QUALITY` | `transcode_quality` |
| `DOUYU_CONFIG` | 指定额外的配置文件路径 |
