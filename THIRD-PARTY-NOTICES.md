# 第三方组件与许可声明

本项目自身代码以 **MIT** 许可发布（见 `LICENSE`）。它依赖并（在二进制发行版中）捆绑了以下第三方组件。

## 1. PySide6 / Qt —— LGPLv3

- 组件：PySide6（Qt for Python）、Qt 6 运行库
- 许可：**GNU Lesser General Public License v3.0**
- 主页：<https://www.qt.io/qt-for-python>
- 许可说明：<https://www.qt.io/licensing/open-source-lgpl-obligations>

### 如果你分发二进制版本，请遵守以下义务

1. 随发行包附带 LGPLv3 与 GPLv3 许可证全文（本仓库 `LICENSES/` 目录，GPLv3 是因为 LGPLv3 以它为基础）。
2. 明确告知使用者该程序使用了 Qt，并说明其 LGPLv3 权利。
3. **允许使用者替换 Qt 库**。因此发布二进制时请使用 **目录版（onedir）**：

   ```
   MCPanel-portable\
     MCPanel-portable.exe
     _internal\PySide6\   <-- Qt 的 dll 都在这里，使用者可以直接替换
   ```

   单文件版（`--onefile`）会把 Qt 库打进 exe 内部，使用者无法替换，严格来说不满足 LGPL 的可替换要求。单文件版建议只用于自己使用或内部传播。

4. Qt 的源代码可从 <https://download.qt.io/> 获取；PySide6 的源码可从 <https://code.qt.io/cgit/pyside/pyside-setup.git/> 获取。

> 说明：LGPL 允许你把本程序以 MIT 发布（动态链接 Qt 并不要求你的代码开源），但上面这些针对 Qt 本身的义务必须履行。

## 2. PyInstaller —— GPLv2 + 例外条款

- 用途：打包成 exe（仅构建期使用）
- 许可：GPL 2.0，附带 bootloader 例外条款，允许用它打包并分发非自由程序
- 主页：<https://pyinstaller.org/>

## 3. Python

- 许可：PSF License Agreement
- 主页：<https://www.python.org/>

## 4. 关于 Minecraft

本程序**不包含任何 Mojang / Microsoft 的游戏文件**（不含 Minecraft 服务端、不含任何贴图、音效、语言文件）。

界面图标（`assets/icon.ico`、`assets/icon.png`）是用 `icongen.py` 以几何图形程序化绘制的草地方块图案，非游戏素材。

"Minecraft" 是 Mojang Studios 的商标。本项目与 Mojang Studios 或 Microsoft **没有任何隶属关系**，也未被其背书。
