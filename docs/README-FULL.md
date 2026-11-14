# 完整包使用说明（解压即用）

> 这个包里**已经带了全部需要的组件**，不需要另外下载任何东西。

## 包里有什么

```
douyulubo-full\
├── douyulubo.exe        主程序（图形界面，内置 Python 解释器）
├── start.bat            备用启动方式
├── README.md            说明书
├── 使用说明.md           你正在读
├── bin\
│   ├── node.exe         内置 Node.js（约 87 MB）
│   ├── ffmpeg.exe       内置 ffmpeg（约 125 MB）
│   └── README.txt       说明
├── douyu.mjs            命令行入口（进阶用）
├── gui\  scripts\  src\  程序文件
└── docs\                详细文档
```

## 怎么用

1. **解压**到任意目录（建议非系统盘，例如 `D:\douyulubo`）
2. 双击 **douyulubo.exe**
3. 「设置」页 → 填**工作目录** → 点「保存设置」
4. 「下载」页 → 顶部粘贴主播链接，如：
   ```
   https://v.douyu.com/author-replay/AbCdEf123456
   ```
   点「识别主播」，会显示主播名字
5. 点「① 抓取录播清单」→「② 获取详细信息」→「③ 开始下载」
   （或者直接点「▶ 一键全部完成」）

## 需要额外装什么吗

**不需要。** 三个组件（Node.js / ffmpeg / Python）都已经在里面了：

| 组件 | 在哪 | 说明 |
|---|---|---|
| Python | 打包进 douyulubo.exe | 抓清单、抓弹幕、转字幕用 |
| Node.js | bin\node.exe | 下载视频、取流用 |
| ffmpeg | bin\ffmpeg.exe | 转封装成 mp4 用 |

程序启动时会优先使用 `bin\` 里的这些文件。

## 体积说明

- zip 约 98 MB，解压后约 231 MB
- 主要体积来自 node.exe（87 MB）和 ffmpeg.exe（125 MB）
- 如果你的电脑本来就装了 Node.js 和 ffmpeg，可以下载「代码包」版本（只有 18 MB）

## 常见问题

| 现象 | 解决 |
|---|---|
| 杀毒软件报警 | 未签名程序常被误判，加信任即可（或自己用源码重新打包） |
| 双击没反应 | 可能被拦截了；右键 → 属性 → 解除锁定，或用 start.bat |
| 提示缺少组件 | 检查 bin\ 里是否有 node.exe 和 ffmpeg.exe，被杀毒软件删了就重新解压 |
| 想换清晰度 | 下载页的「清晰度」下拉框，默认优先最高 |
