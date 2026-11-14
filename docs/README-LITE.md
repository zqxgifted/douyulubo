# 代码包使用说明（体积小，自动使用你电脑上的组件）

> 这个包**只包含程序本身**（约 18 MB），需要你电脑上已有
> **Node.js**、**ffmpeg**、**Python** 三个组件。
>
> **如果你的电脑已经装了它们，这个包开箱即用，不用再下载任何东西。**
> 程序会自动找到它们。

---

## 一、先看看你电脑有没有

程序启动时会自动检查。你也可以手动确认：

打开「命令提示符」(Win+R 输入 `cmd`)，逐条粘贴执行：

```bat
node --version
ffmpeg -version
python --version
```

| 结果 | 说明 |
|---|---|
| 三条都显示版本号 | ✅ 你三个都有，直接用本包即可 |
| 某条提示"不是内部或外部命令" | ❌ 缺那个组件，看下面第二节 |

---

## 二、缺组件怎么办

### 方式 A：安装到系统（推荐，一次装好以后都能用）

| 组件 | 官方下载地址 | 安装注意 |
|---|---|---|
| **Node.js** | https://nodejs.org/zh-cn/download ｜ 官网首页：https://nodejs.org/ | 下载 **LTS** 版（长期支持版），一路默认下一步即可 |
| **ffmpeg** | https://ffmpeg.org/download.html ｜ Windows 预编译包：https://github.com/BtbN/FFmpeg-Builds/releases ｜ 官方推荐的其他二进制：https://ffmpeg.org/download.html#build-windows | 下载 `ffmpeg-master-latest-win64-gpl.zip`，解压后把 `bin` 文件夹里的 `ffmpeg.exe` 加到系统 PATH |
| **Python** | https://www.python.org/downloads/windows/ ｜ 官网首页：https://www.python.org/ | 安装时**务必勾选**「Add Python to PATH」 |

**补充说明**

- **Node.js 官网**：https://nodejs.org/ （中文页 https://nodejs.org/zh-cn/ ）
- **ffmpeg 官网**：https://ffmpeg.org/ （下载页 https://ffmpeg.org/download.html ）
  - Windows 用户建议用 BtbN 的预编译包：https://github.com/BtbN/FFmpeg-Builds/releases
  - 下载文件名形如 `ffmpeg-master-latest-win64-gpl.zip`，解压后 `bin\ffmpeg.exe` 就是需要的文件
- **Python 官网**：https://www.python.org/ （Windows 下载页 https://www.python.org/downloads/windows/ ）
  - 本包的 `douyulubo.exe` 已内置 Python，**只有你想用命令行功能时才需要单独装 Python**

**ffmpeg 加到 PATH 的方法**（稍微麻烦一点）：

1. 把解压出来的文件夹放到比如 `C:\ffmpeg`
2. Win+R 输入 `sysdm.cpl` → 高级 → 环境变量
3. 在「系统变量」里找到 `Path` → 编辑 → 新建
4. 填入 `C:\ffmpeg\bin` → 确定
5. **重新打开命令提示符**，执行 `ffmpeg -version` 验证

> 不想折腾 PATH？用下面的方式 B，更简单。

### 方式 B：直接放进 bin 文件夹（最简单）

1. 在解压目录里找到 `bin` 文件夹（已经建好了）
2. 把这些文件直接复制进去：

```
douyulubo-full\bin\
├── node.exe      ← 从 Node.js 安装目录复制（一般在 C:\Program Files\nodejs\）
└── ffmpeg.exe    ← 从 ffmpeg 解压包里复制
```

3. 重新打开 `douyulubo.exe`

**程序会优先使用 `bin\` 里的文件**，放进去了就一定能识别。

> Python 不用管：本包的 `douyulubo.exe` 已经内置了 Python 解释器，
> 只有你想用命令行功能时才需要系统 Python。

---

## 三、程序的自动查找顺序

启动时，对每个组件按这个顺序找：

```
① bin\ 文件夹            ← 你手动放的，优先级最高
② 系统 PATH              ← 正常安装并加了环境变量就能找到
③ 常见安装位置            ← 例如 C:\Program Files\nodejs\node.exe
④ config.json 里指定的路径  ← 仅 ffmpeg 支持
```

找到就用，找不到会在界面上提示你缺哪个、去哪下载、放哪里。

「设置」页点「检查运行环境」可以随时看到每个组件的**实际路径和来源**：

```
✔ Node.js   ：系统 PATH：C:\Program Files\nodejs\node.exe
✔ ffmpeg    ：包内自带：D:\douyulubo\bin\ffmpeg.exe
✔ Python    ：包内自带：D:\douyulubo\douyulubo.exe
```

---

## 四、怎么用

1. **解压**到任意目录
2. 双击 **douyulubo.exe**
3. 「设置」页 → 填**工作目录** → 「保存设置」
4. 点「检查运行环境」，确认三个组件都是 ✔
5. 「下载」页 → 粘贴主播链接 → 「识别主播」
6. 点「① 抓取录播清单」→「② 获取详细信息」→「③ 开始下载」

## 五、和完整包的区别

| | 代码包（本包） | 完整包 |
|---|---|---|
| 体积 | 约 18 MB | 约 98 MB |
| Python | exe 内置 | exe 内置 |
| Node.js | 用你电脑的 / 自己放 bin | 包内自带 |
| ffmpeg | 用你电脑的 / 自己放 bin | 包内自带 |
| 适合谁 | 电脑已装过这些工具，或不想下大文件 | 想开箱即用、不想折腾 |

两个包功能**完全一样**，只是依赖组件的来源不同。
