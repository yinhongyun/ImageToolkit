# ImageToolkit 技术选型调研

面向需求：图片裁剪、拆分、边缘透明、同图多区域尺寸识别、格式转换等本地图片操作。

## 结论（推荐）

**首选：Python + PySide6（或 CustomTkinter）+ Pillow + OpenCV + NumPy**

适合个人/小团队快速做出可用的 Windows 桌面工具，图像算法生态成熟，同类开源（精灵图拆分、图标提取）大多也走这条路。

若以后要做成更精致的跨平台商业桌面端，可再迁移为：

**备选：Tauri 2 + React/Vue + Rust 图像库（或调用 Python 子进程）**

## 需求与能力映射

| 功能 | 推荐实现 |
|------|----------|
| 裁剪 / 区域框选 | Pillow `crop` + UI 画布交互 |
| 网格拆分 | 固定宽高切格；或按间距自动估格 |
| 连通区域拆分 / 识别不同位置图块大小 | OpenCV 轮廓 / 连通分量；或按 alpha 透明分隔 |
| 边缘透明 / 去背景 | 边缘 flood-fill、色键、或 rembg（复杂背景） |
| 格式转换 | Pillow / imageio（PNG/JPEG/WebP/BMP 等） |
| 批处理 | Python 脚本层，GUI 只做参数与预览 |

## 方案对比

### A. Python 桌面（推荐起步）

- **UI**：PySide6（更专业）或 CustomTkinter（更轻）
- **图像**：Pillow（读写/裁剪/格式）、OpenCV（检测/轮廓）、NumPy（像素运算）
- **优点**：开发快；OpenCV 对「一张图里多块区域」天然合适；Windows 上手成本低
- **缺点**：打包体积偏大（PyInstaller/Nuitka）；UI 精致度不如 Web 前端
- **适合**：工具型、本地批处理、算法优先

### B. Electron + TypeScript

- **UI**：React + Canvas / Cropper 类库
- **图像**：sharp（主进程）、或浏览器 Canvas/WebGL
- **优点**：界面迭代快；TS 全栈统一
- **缺点**：安装包与内存占用大；复杂 CV 不如 Python/OpenCV 顺手
- **适合**：偏设计稿交互、强 UI、弱算法

### C. Tauri 2 + Web 前端

- **UI**：React/Vue + WebView2（Windows）
- **图像**：Rust `image` crate，或 sidecar 调 Python/OpenCV
- **优点**：包体小、内存低；2026 新项目常见首选之一
- **缺点**：重算法时要么写 Rust，要么再挂 Python，架构更复杂
- **适合**：确定要长期做跨平台精致桌面产品时

### D. .NET / WPF 或 Avalonia

- **优点**：Windows 原生体验好；与现有 Unity/C# 技能可部分复用
- **缺点**：OpenCV 绑定与生态不如 Python 方便；跨平台要用 Avalonia
- **适合**：团队已是 .NET 主力、主要只做 Windows

## 建议落地路径

1. **MVP（2～3 周量级）**：Python + PySide6 + Pillow + OpenCV  
   - 打开图片 → 预览 → 手动裁剪 → 网格拆分 → 透明边缘 → 导出格式
2. **第二期**：自动检测同图多区域（连通域 / alpha 分隔）并列出宽高  
3. **第三期**：批处理、拖拽、预设、命令行  
4. **产品化阶段再评估**：是否值得迁到 Tauri（UI）+ 保留 Python 算法服务

## 不推荐作为主方案

- 纯浏览器网页：本地大文件、批量导出、文件系统权限体验差（除非明确只要在线）
- 纯 Unity：过重，不适合做通用图片工具
