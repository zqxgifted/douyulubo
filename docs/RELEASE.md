# 解压即用版（Windows）

[← 返回 README](../README.md) ｜ [GUI](GUI.md) ｜ [弹幕转换](DANMAKU.md)

GitHub Releases 里提供的 `斗鱼录播工具箱_vX.Y.Z_win-x64.zip` 是**自包含**的：
解压后双击 exe 即可使用，**不需要安装 Python、Node.js 或 ffmpeg**。

## 里面有什么

```
斗鱼录播工具箱\
├── 斗鱼录播工具箱.exe        图形界面 + 内置 Python 解释器（含 requests）
├── 启动.bat                  备用启动方式
├── 使用说明.txt              一分钟上手
├── bin\
│   ├── node.exe              内置 Node.js（脚本运行用，约 87 MB）
│   └── ffmpeg.exe            内置 ffmpeg（TS→MP4 转封装，约 125 MB）
├── douyu.mjs                 命令行入口
├── scripts\  src\  gui\      脚本与模块
├── examples\                 示例配置
└── docs\                     使用文档
```

zip 约 98 MB，解压后约 231 MB。

## 为什么能做到自包含

同一个 exe 有两种用法：

| 调用方式 | 行为 |
|---|---|
| 双击 / 无参数 | 启动 Tkinter 图形界面 |
| `--run-py <脚本> [参数]` | 当作 `python.exe` 用，执行 Python 脚本 |

原理：PyInstaller 把 Python 解释器、标准库、tkinter、requests 打进 exe。
GUI 启动时把环境变量 `DOUYU_PY` 指向自己，于是 `douyu.mjs` 调用
`step1/step2/step4` 等 Python 脚本时，走的就是这个内置解释器。
`bin\` 目录会被加入 `PATH`，所以 node 与 ffmpeg 也能直接找到。

## 第一次使用

1. 双击 `斗鱼录播工具箱.exe`
2. 「配置」页 → 点「从示例初始化」→ 填 **主播 ID** 和 **工作目录** → 「保存配置」
3. 点「环境自检」，应显示：内置 Python ✔ / 内置 requests ✔ / node ✔ / ffmpeg ✔
4. 「运行 / 命令」页：
   - **弹幕处理** 下拉框默认「下载弹幕并转换 ASS 格式」
   - **清晰度** 下拉框默认「优先最高清晰度」
   - 点 `fetch` → `detail` 抓清单，再点 `run` 一键跑完
5. 「下载管理 / 历史」页查看已下载的录播；重复下载会提示「已下载」

## 用命令行（可选）

解压目录下：

```bat
bin\node.exe douyu.mjs --help
bin\node.exe douyu.mjs doctor
bin\node.exe douyu.mjs run
```

若用自带 exe 当解释器跑 Python 脚本：

```bat
set DOUYU_PY=%CD%\斗鱼录播工具箱.exe
set PATH=%CD%\bin;%PATH%
```

## 常见问题

| 现象 | 说明 |
|---|---|
| 杀毒软件报警 | PyInstaller 打包的 exe 常被误判（无签名），加信任即可；也可自行用 `build_release.ps1` 重新打包 |
| 双击没反应 | 看是否有旧的同名进程残留；或在 cmd 里运行看报错 |
| ffmpeg 缺失警告 | 发布包应包含 `bin\ffmpeg.exe`；若被误删，自行下载放入 `bin\` |
| 想换清晰度 | 「清晰度」下拉默认最高；先跑 `probe`（仅探测元数据）后点「刷新档位」可列出实际可选档位 |
| 数据在哪 | 都在你配置的「工作目录」下：`data / downloads / danmaku / danmaku_ass` |

## 自己打包

仓库根目录提供构建脚本（需要本机有 Python + PyInstaller + Node + ffmpeg）：

```powershell
powershell -ExecutionPolicy Bypass -File build_release.ps1
```

产物在 `dist\`：目录版 + zip。脚本会依次复制源码、内置 node/ffmpeg、
用 `build_exe.spec` 打包 exe、生成说明文件并压缩。
