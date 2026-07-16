# 净页 JingYe

面向**扫描版 / 图片型 PDF** 的选色清理桌面工具：按颜色替换浅色水印与杂质，支持区域遮盖、灰度、**组合多步一次导出**与批量处理。

> **免责声明**：请仅处理你有权处理的文档。本工具采用光栅化路线，导出多为**图片型 PDF**（通常不可再选中文字）。使用后果由使用者自行承担。

| 项 | 内容 |
| --- | --- |
| 中文名 | **净页** |
| 英文名 | **JingYe** |
| 包名 | `pdf_dewatermark` |
| 许可证 | [MIT](./LICENSE) |
| 当前版本 | 见 `src/pdf_dewatermark/__init__.py` / [Releases](../../releases) |
| 详细使用说明 | [博客：扫描版 PDF 选色去水印工具说明](https://blog.yilanapp.com/posts/adbbe073/) |

---

## 适合 / 不适合

**适合**

- 整页是扫描图或伪扫描（几乎选不中字）
- 正文上的浅灰半透明公号字、浅色 logo、固定页眉页脚条

**不太适合**

- 编辑器可一键删除的矢量水印 / 注释水印（优先用阅读器自带功能）
- 需要保留可选中文字、可检索的 PDF（本工具会光栅化）

---

## 功能一览

| 模块 | 说明 |
| --- | --- |
| **选色替换** | 多组「目标色 → 背景色」、容差、预览、单页 / 范围 / 全部 |
| **区域遮盖** | 矩形纯色遮盖；可应用到全部 / 奇偶 / 隔页 / 自定义页码 |
| **灰度转换** | 整本转灰度图 PDF |
| **组合处理** | 灰度 · 选色 · 区域在同一渲染上按序处理，**一次导出** |
| **批量** | 多文件共用选色页参数队列导出 |

---

## 环境要求

- Windows 10/11（GUI 与打包脚本按 Windows 编写）
- Python **3.10+**（开发机推荐 3.12）
- 可选：[GitHub CLI (`gh`)](https://cli.github.com/) — 用于一键创建仓库 / 上传 Release

---

## 环境准备与启动

### 方式一：一键脚本（推荐）

在项目根目录 PowerShell 中：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_setup.ps1
```

脚本会创建 `.venv`、安装依赖（含 GUI）、可编辑安装本包。

### 方式二：手动

```powershell
cd <本项目目录>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[gui,dev]"
```

### 启动 GUI

```powershell
# 已激活 venv 时
python -m pdf_dewatermark

# 或
.\run_gui.bat
```

入口也可使用：

```powershell
jingye
pdf-dewatermark-gui
```

### 命令行示例

```powershell
pdf-dewatermark-cli remove 输入.pdf --r 200 --g 200 --b 200 --tolerance 30 -o 输出.pdf
```

应用内：**帮助 → 使用说明** 会打开完整在线文档。

---

## 使用步骤（极简）

1. 顶栏 **打开** 扫描 PDF（全局共用一本）
2. **选色替换**：吸管点水印色 → 调容差 → 可选「效果」预览
3. 若有固定页眉：到 **区域遮盖** 画框 → **应用到…**
4. 若要多步：到 **组合处理** 勾选步骤 → **组合导出**
5. 导出预设默认 **均衡**（约 200 DPI + JPEG；扫描页默认不高于原图分辨率）

更多参数、工作流与 FAQ 见：[使用说明（博客）](https://blog.yilanapp.com/posts/adbbe073/)。

---

## 项目结构

采用标准 **src layout**：

```text
.
├── src/pdf_dewatermark/     # 可安装 Python 包
│   ├── core/                # 选色 / 区域 / 灰度 / 页码等算法
│   ├── pdf/                 # 打开、渲染、导出 DPI
│   ├── gui/                 # PySide6 + Fluent 界面
│   ├── cli.py               # 命令行
│   ├── processor.py         # 业务编排（含组合流水线）
│   └── models.py
├── tests/                   # pytest
├── docs/                    # 设计与开发说明
├── legacy/                  # 改造前脚本（参考）
├── packaging/               # PyInstaller / 元数据 / Inno 可选
├── scripts/                 # 开发、开源初始化、构建与发布
├── pyproject.toml
├── LICENSE                  # MIT
└── README.md
```

**不会**提交到 Git 的内容（见 `.gitignore`）：`.venv/`、`build/`、`dist/`、用户 `output/`、日志、个人 PDF、本地偏好等。  
**预编译安装包**请到 GitHub **Releases** 下载，不要从仓库里找 `dist/`。

---

## 自构建 / 打包（绿色 zip）

```powershell
# 建议先 dev_setup，再：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_gui_onedir.ps1
```

产物（均在本地 `dist/`，**默认不进 Git**）：

| 路径 | 含义 |
| --- | --- |
| `dist/JingYe/JingYe.exe` | 最新可运行目录 |
| `dist/releases/JingYe-x.y.z.zip` | 对外分发用压缩包 |

使用：解压 zip 后**保留整个文件夹**，运行 `JingYe.exe`。

可选 Windows 安装包（需本机 [Inno Setup 6](https://jrsoftware.org/isinfo.php)）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

更细说明见 `docs/04-打包与分发.md`。

---

## 开源到 GitHub / 发布 Release（推荐流程）

### 你需要准备什么

1. 一个 **GitHub 账号**
2. 在网页上 **新建空仓库**（不要勾选自动添加 README，避免与本地冲突），或让脚本引导创建  
3. 本机已安装 **Git**；若要用一键发 Release，再装 **[GitHub CLI](https://cli.github.com/)** 并 `gh auth login`

### 首次：初始化并配置远程（交互）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\open_source_init.ps1
```

脚本会交互完成大致这些事：

- `git init`（若尚未初始化）
- 检查 `.gitignore`，提示是否有不该提交的大文件 / PDF
- 可选：输入远程地址 `https://github.com/<你>/<仓库>.git` 并 `git remote add origin`
- 若已安装 `gh`：可选择 `gh repo create` 创建远程仓库
- 引导首次 `git add` / `commit`（**默认不自动 push**，需你确认）

### 日常：构建并发布最新包到 Releases

```powershell
# 构建 + 打 tag + 用 gh 上传最新 zip（有确认提示）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1

# 只构建不发布
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -BuildOnly

# 只检查待提交文件是否干净
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -CheckOnly
```

策略（方案 A）：

- **Git 仓库**：源码、文档、脚本  
- **GitHub Releases**：仅挂载**当前版本**的 `JingYe-x.y.z.zip`  
- 旧 zip 保留在 GitHub Release 历史即可，不必塞进 Git

没有 `gh` 时：脚本仍可构建并打印「请到网页手动上传 zip」的路径。

---

## 测试

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

---

## 技术栈

- Python 3.10+
- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) · NumPy · Pillow
- GUI：PySide6 · [QFluentWidgets](https://qfluentwidgets.com/)
- 打包：PyInstaller（onedir）

---

## 贡献

欢迎 Issue / PR：修 bug、改进文档、补充测试均可。较大改动建议先开 Issue 讨论。  
提交前请确认未把个人 PDF、`data/gui_prefs.json`、`dist/` 等纳入版本库。

---

## 致谢

- 本项目在 **[Linux.do](https://linux.do/)** 社区分享与交流，欢迎同好反馈与讨论。  
- 完整图文说明发布于：[以蓝博客](https://blog.yilanapp.com/posts/adbbe073/)  
- 依赖与开源生态：PyMuPDF、Qt/PySide、QFluentWidgets、PyInstaller 等

---

## License

[MIT License](./LICENSE) © 2026 净页 JingYe contributor(s)
