# ImageToolkit

本地图片拆分工具：自动/手动拆图、范围预览、背景透明、多格式导出、`.itk` 工程保存。

## 环境

- Python 3.11+
- Windows（已在 Win10 验证）

## 安装

```bash
cd D:\ImageToolkit
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 启动

```bash
python src\app.py
```

## 主要功能

- 打开 / 拖拽 / **Ctrl+V 粘贴**导入图片
- **自动识别**多块前景并框选
- **手动**：悬停吸附、手动画框、手柄调节
- 透明预览（棋盘格）与边框范围预览
- 导出 PNG / WebP / JPEG / BMP（PNG 优先）
- 保存 / 打开 **`.itk` 工程**（切片框与参数）

## 快捷键

| 键 | 动作 |
|----|------|
| Ctrl+O | 打开图片 |
| Ctrl+V | 粘贴剪贴板图片 |
| A | 自动识别 |
| V / R | 选择 / 画框 |
| Ctrl+E | 导出 |
| Ctrl+S | 保存工程 |
| Delete | 删除切片 |
| 空格+拖 | 平移画布 |
| Ctrl+0 | 适应窗口 |
| C（按住） | 临时隐藏边框 |

## 文档

- `docs/product-design.md` — 产品与交互设计
- `docs/tech-stack.md` — 技术选型

## 样例

`samples/character_sheet.png` — 角色三视图测试图
