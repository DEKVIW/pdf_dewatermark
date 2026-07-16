# GUI 开发说明（净页 JingYe）

> **状态**：与代码同步的真实说明（非早期设想稿）  
> **基准版本**：0.2.2  
> **代码根**：`src/pdf_dewatermark/gui/`  
> **入口**：`python -m pdf_dewatermark` → `gui.app:main`

本文描述**当前已实现**的 GUI 结构、分层、页面职责、关键交互与扩展约定。若与早期 `02-架构设计.md` 冲突，**以本文 + 源码为准**。

---

## 1. 技术选型（已落地）

| 项 | 选择 | 说明 |
| --- | --- | --- |
| UI 框架 | **PySide6** | Qt 绑定，桌面成熟 |
| 控件库 | **PySide6-Fluent-Widgets**（`qfluentwidgets`） | 导航、主按钮、分段控件等 |
| 线程 | `QThread` + `JobWorker` | 长任务不卡 UI |
| PDF 渲染 | PyMuPDF (`fitz`) | 页面 pixmap / 连续滚动懒渲染 |
| 图像处理 | Pillow + NumPy | 取色缓冲、选色算法在 core |

工程上借鉴 `video-quick-eval` 的 **src 布局 + Fluent 导航 + Worker 调 core**，交互按 PDF 工作台重做（画布/连续滚动/取色），不是「表单 + 日志 + 开始」。

---

## 2. 目录与职责

```text
src/pdf_dewatermark/gui/
├── app.py                 # 启动：路径 bootstrap、Theme、QApplication
├── branding.py            # 产品名、版本、图标路径
├── icons.py               # FluentIcon 统一映射（禁止各页硬编码散落）
├── theme.py               # 字号 4 档、间距、工具栏/空状态/状态栏样式
├── main_window.py         # 壳层：菜单、应用工具栏、导航、状态栏、任务编排
├── workers.py             # JobRequest / JobWorker / start_job
├── pages/
│   ├── remove_page.py     # 选色替换（主工作台）
│   ├── region_page.py     # 区域遮盖
│   ├── grayscale_page.py  # 灰度转换
│   ├── pipeline_page.py   # 组合处理（多步一次导出）
│   └── batch_page.py      # 批量（可从选色页同步参数）
├── widgets/
│   ├── continuous_view.py # 连续滚动 PDF 视图（懒渲染 + 精准取色）
│   ├── empty_state.py     # 未打开文档的空状态
│   ├── params_panel.py    # 多组颜色参数抽屉
│   ├── log_panel.py       # 日志
│   └── pdf_canvas.py      # 单页画布工具（取色光标等，区域/历史逻辑复用）
├── state/
│   └── prefs.py           # gui_prefs.json、最近文件
└── resources/
    ├── app.ico
    └── app.png
```

### 依赖方向（强制）

```text
gui  →  processor / models / pdf / core
gui  ↛  禁止在页面里复制选色算法
core ↛  禁止依赖 gui
```

长任务只通过 `workers.JobRequest` 调 `processor.*`，不要在 UI 线程里跑整本 PDF。

---

## 3. 壳层布局（规范分层）

与常见文档/阅读器一致，分三层：

```text
┌ 菜单栏：文件 / 视图 / 帮助 ─────────────────────────────────┐
├ 应用工具栏（壳层）：打开 | 当前文件名 | 输出目录 | 停止 ──────┤
├ 左侧导航：选色 | 区域 | 灰度 | 组合处理 | 批量 ───────────────┤
├ 页面标题 + 副标题 ──────────────────────────────────────────┤
├ 内容区（QStackedWidget）
│    无文档 → EmptyState（打开 / 拖入 / Ctrl+O）
│    有文档 → 文档工具栏 + 主视图 +（可选）参数抽屉
├ 状态栏：状态文字 | 进度条 | 日志开关 ────────────────────────┘
```

| 层级 | 放什么 | 不放什么 |
| --- | --- | --- |
| 菜单 / 应用工具栏 | 打开、最近文件、输出目录、退出 | 容差、翻页细节 |
| 文档工具栏 | 页导航、缩放、原图/效果、参数、处理 | 常驻操作说明书式提示 |
| 主区域 | 连续滚动预览 / 取色 / 空状态 | 堆满杂项设置 |
| 状态栏 | 状态、进度、日志折叠 | 大块常驻日志 |

**打开文件入口（多入口，规范组合）**：

1. `文件 → 打开 PDF…`（Ctrl+O）  
2. 应用工具栏「打开」  
3. 空状态主按钮  
4. 拖入窗口 / 空状态区域  
5. `文件 → 最近打开`

实现集中在 `MainWindow.open_pdf_path`（**全局 Document**）：选色/区域 `attach_document`，不各自 `fitz.open`/`close`。  
子页空状态打开 → `open_pdf_requested` → 主窗口。换文档时清空区域矩形，保留选色参数。

---

## 4. 页面说明

### 4.1 选色替换 `RemovePage`（主功能）

| 项 | 实现 |
| --- | --- |
| 文件 | `pages/remove_page.py` |
| 视图 | `ContinuousPdfView` 连续滚动 |
| 参数 | 右侧抽屉 `ParamsPanel`（默认收起，首次取色可自动展开） |
| 空/有文档 | `QStackedWidget`：0=EmptyState，1=工作台 |

**文档工具栏**：上一页 / 下一页 / 缩放 −+ / 适宽 / 原图|效果 / 参数 / 刷新效果 / 处理当前页|页范围|处理全部。

**交互约定**：

| 操作 | 行为 |
| --- | --- |
| 滚轮 | 纵向滚动文档 |
| Ctrl+滚轮 | 缩放 |
| 空格 / 中键拖拽 | 平移（不在工具栏写提示文案） |
| 右侧/底侧细滚动条 | 拖滑块快速定位（约 8px，避免粗条挤内容） |
| 单击（取色模式） | 从**显示用 1:1 原图缓冲**取样 RGB |
| 原图 / 效果 | 效果 = 对可见页懒处理，非整本一次算完 |

**信号**：

- `status` / `log` / `request_job` → 主窗口  
- `document_changed(Path|None)` → 更新壳层文件名与标题  

**处理任务**：`JobRequest(kind="remove", params=RemoveParams, page_indices=...)`。

### 4.2 区域遮盖 `RegionPage`

| 项 | 实现 |
| --- | --- |
| 视图 | 同一套 `ContinuousPdfView` |
| 绘制 | `set_draw_rect_mode(True)`，`rect_drawn(page, x0,y0,x1,y1)` 归一化坐标 |
| 叠层 | `set_process_fn` 在原图上画半透明矩形（效果通道懒渲染） |
| 应用范围 | **应用到…** 对话框：全部 / 奇数页 / 偶数页 / 从当前页隔页 / 自定义页码；可选替换目标页已有区域 |
| 其它 | 清除本页区域、清除所有区域、导出 |

页码解析与模板复制：`core/page_ranges.py`（`resolve_apply_pages` / `apply_region_templates`）。  
对话框：`widgets/apply_regions_dialog.py`。

任务：`kind="region"` + `regions` + `region_dpi`。

### 4.3 灰度 `GrayscalePage`

表单式：选输入/输出路径 + DPI → `kind="grayscale"`。全局打开 PDF 时会预填输入路径，仍可另选文件单独导出。

### 4.4 组合处理 `PipelinePage`

| 项 | 说明 |
| --- | --- |
| 文档 | 使用主窗口**全局当前 PDF**（与选色/区域同一份） |
| 步骤 | 灰度 / 选色 / 区域：可勾选、可上移下移调序 |
| 配置 | 颜色组来自选色页；矩形来自区域页；灰度仅勾选即可 |
| 导出 | `kind="pipeline"` → `process_pdf_pipeline`：每页渲一次、内存串行步骤、写一次 PDF |
| 单页导出 | 选色/区域/灰度页原有导出**不变** |

### 4.5 批量 `BatchPage`

- 文件队列 + 输出目录  
- **从选色页同步**：`sync_requested` → 主窗口取 `remove_page.params.build_params()`  
- 切到批量模式时也会静默同步一次  
- 优先用同步后的多组 `ColorPair`；否则用界面备用单组 RGB  

任务：`kind="batch_remove"`。

---

## 5. 连续滚动与取色（重点）

### 5.1 实现文件

`widgets/continuous_view.py` → 类 `ContinuousPdfView`

### 5.2 渲染策略（阅读器范式，0.2.2）

1. **占位布局**：按页宽高比算每页高度，拼成长卷（不先渲完全部页）。  
2. **可见区 + 缓冲 1 页** 才真正 `get_pixmap`。  
3. **像素预算 LRU** 控制 pixmap / PIL（大缩放自动少留页）。  
4. **按屏幕 DPR 精渲**：物理宽 = 逻辑页宽 × `devicePixelRatio`，`QPixmap.setDevicePixelRatio`，高分屏不发糊。  
5. **缩放**：保留旧图，`SmoothPixmapTransform` 过渡；防抖后再按新尺寸精渲（**禁止** Fast 糊占位导致清晰↔模糊抖动）。  
6. 导出仍走 `processor` 独立 DPI，与预览分辨率分离。  

### 5.3 取色策略（必须遵守）

错误做法：点击坐标 → 另一套 DPI 重渲 → 再 getpixel（易偏）。  

正确做法（当前实现）：

1. 命中测试含**横向滚动**与页内**逻辑**坐标；  
2. 保证该页已有 **当前 DPR 下的原图 PIL 缓冲**；  
3. 逻辑坐标映射到物理像素后取样；边缘可用 3×3 中位抗锯齿噪点；  
4. 通过 `color_sampled(page, r, g, b)` 交给页面写参数；  
5. **始终从原图取样**，不从效果图取样。  

页面侧请接 `color_sampled`，不要自己再反算一套坐标。

### 5.4 效果模式与性能

| 模式 | 行为 |
| --- | --- |
| 原图浏览 | 可见页按 DPR 精渲；滚动防抖补渲 |
| 缩放 | 旧图平滑拉伸跟手 → **约 60ms 合并**后精渲（主线程 fitz） |
| 效果 | 原图先显示；选色在 **QThreadPool** 异步；**与原图同分辨率**（0.2.2 起取消半分辨率预览） |
| 改参数 | **180ms 防抖** 再刷效果 |
| 导出 | Worker 全量处理；导出 DPI 不受预览影响 |

卡顿排查：原图滚动相对轻；效果模式重在算法；缩放不应同步堵死 UI。

---

## 6. 参数与模型

### 6.1 UI：`ParamsPanel`

- 多组 **颜色组**（`ColorPair`：目标色样本列表 + 背景色）  
- 匹配：颜色点选 / 色阶阈值、容差、对比度  
- 输出：**导出预设**（均衡/高清/小体积/自定义）+ DPI/分辨率×、格式、JPEG 质量、扫描不放大  
- 默认 **均衡**：JPEG 质量 92 · 200 DPI · 扫描页 DPI 不超过原图  
- 可选：填充方式、去噪/补洞（默认硬替换 + 0/0）  

`build_params()` → `RemoveParams`（含 `pairs`、导出字段）。  
智能 DPI：`pdf.render.resolve_export_dpi`。

### 6.2 算法侧

- `models.RemoveParams` / `ColorPair`  
- `core.remove.remove_watermark_*`  
- 预览与导出共用算法；预览 DPI/范围可以不同。  

---

## 7. 主题与图标

### 7.1 字号（仅 4 档）

定义在 `theme.py`：

| 档位 | 字号 | 用途 |
| --- | --- | --- |
| TITLE | 16pt | 页面标题 |
| SECTION | 13pt | 分组标题、文件名 |
| BODY | 12pt | 正文、按钮、表单 |
| CAPTION | 11pt | 状态、页码、次要说明 |

控件高度统一约 `CTRL_HEIGHT = 32`。

### 7.2 图标

- 应用图标：`resources/app.ico` / `app.png`，打包用 `packaging/app.ico`  
- 功能图标：只从 `icons.py` 引用 FluentIcon  

新增导航或工具按钮时：**先加 `icons.py` 常量，再在页面使用**。

### 7.3 品牌

`branding.py`：`APP_NAME_ZH=净页`、`APP_NAME_EN=JingYe`、`APP_VERSION` 等。  
改版本号时同步：`branding.py`、`__init__.py`、`pyproject.toml`。

---

## 8. 偏好与数据

| 项 | 路径 |
| --- | --- |
| GUI 偏好 | `data/gui_prefs.json`（相对应用根） |
| 最近文件 | `prefs.recent_files`（`push_recent`） |
| 输出默认 | `output/` |

`paths.get_app_root()`：开发时为项目根；打包后为 exe 所在目录。

---

## 9. 后台任务

`workers.py`：

| kind | 调用 |
| --- | --- |
| `remove` | `process_pdf_remove` |
| `grayscale` | `process_pdf_grayscale` |
| `region` | `process_pdf_regions` |
| `pipeline` | `process_pdf_pipeline` |
| `batch_remove` | `process_batch_remove` |

信号：`progress` / `log_line` / `finished_ok` / `failed`；支持 `request_cancel`。

主窗口 `start_job` 负责：进度条、停止按钮、完成后询问打开文件夹。

---

## 10. 开发与调试

```powershell
# 可编辑安装 + GUI 依赖
pip install -e ".[gui]"

# 启动
python -m pdf_dewatermark
# 或
.\run_gui.bat
```

建议：

- 改算法：写/跑 `tests/test_core_remove.py`，不要只靠肉眼  
- 改取色/滚动：用真实多页 PDF 测命中与缩放是否白屏  
- 改 UI 文案：不要写「旧版」等实现细节给用户  

---

## 11. 扩展清单（改 GUI 时）

新增一个导航页时：

1. `pages/xxx_page.py`：提供 `status` / `log` / `request_job`（若需）  
2. `main_window.py`：MODE 常量、LABELS、stack、导航项  
3. `icons.py`：导航图标  
4. 长任务走 `JobRequest` + `processor`  
5. 更新本文对应小节  

修改取色时：

1. 优先改 `continuous_view` 的 1:1 缓冲与 `color_sampled`  
2. 不要在页面里用另一套 DPI 重渲再取色  

---

## 12. 已知边界（写进文档避免误解）

- 导出结果多为**图片型 PDF**，一般不可选中文字  
- 连续滚动是**浏览体验**；导出仍按页在 Worker 中处理  
- 效果模式可见页处理有成本，极快滚动时可能短暂旧图平滑拉伸  
- **分发 / 构建**：见 **`04-打包与分发.md`**（主推 zip 绿色包；Inno 可选；含技术栈与 `.spec` 说明）。本文不重复打包步骤。  

---

## 13. 相关文档

| 文档 | 关系 |
| --- | --- |
| `02-架构设计.md` | 总架构；GUI 细节以本文为准 |
| `06-产品与图标.md` | 产品名与图标资源 |
| `03-效果优化方案.md` | 算法策略 |
| `04-打包与分发.md` | **打包技术说明**（PyInstaller onedir、zip、可选 Inno）；GUI 发版细节见该文 |
| `05-实施路线.md` | 阶段与未做增强项 |
| `legacy/` | 历史 Tk 脚本，仅参考，不进主 GUI 路径 |
