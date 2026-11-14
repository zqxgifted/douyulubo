# gui/

图形界面（tkinter，零第三方依赖）。

| 文件 | 说明 |
|---|---|
| `app.py` | 主窗口与全部界面逻辑 |
| `result_tree.py` | 搜索结果树（场次 → 分段，支持勾选/分页） |
| `theme.py` | Material Design 风格主题 |
| `deps.py` | 依赖探测（node / ffmpeg 路径解析） |
| `launcher.py` | 双模式入口：无参数开 GUI，`--run-py` 当 Python 解释器 |
| `make_icon.py` | 生成蓝色鲸鱼图标（`.ico` / `.png`） |
| `whale.ico` / `whale.png` | 程序图标 |
| `launch_gui.bat` | 源码方式启动的批处理 |

## 双模式说明

打包后的 `douyulubo.exe` 有两种用法：

```
双击                              → 打开 GUI
douyulubo.exe --run-py xxx.py     → 当作 Python 解释器执行脚本
```

第二种模式让完整包不必额外携带 `python.exe`。
