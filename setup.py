# -*- coding: utf-8 -*-
"""
Minecraft 控制面板 —— 安装程序（带向导）

设计约束（很重要）：
  1. 面板必须能找到 server.properties，所以安装位置由「你的服务端目录」决定，
     本程序只往 <服务端目录>\\panel\\ 里写东西，绝不碰 world / mods / config。
  2. 卸载走 panel.exe --uninstall，卸载时默认保留 backups。
  3. 不写系统路径、不要求管理员权限、不装任何驱动或服务。
"""
import base64
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

APP_NAME = "Minecraft 控制台"
VERSION = "1.1.0"
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPanel"
NO_WINDOW = 0x08000000

FROZEN = getattr(sys, "frozen", False)


def res_dir() -> Path:
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


PAYLOAD = res_dir() / "payload" / "MCPanel.exe"


# ---------------------------------------------------------------- Win32
def msg(text: str, title: str = APP_NAME + " 安装程序", flags: int = 0x40) -> int:
    """0x40 信息 / 0x30 警告 / 0x10 错误；0x24=是否 / 0x23=是否取消"""
    try:
        return int(ctypes.windll.user32.MessageBoxW(None, text, title, flags))
    except Exception:
        print(text)
        return 1


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [
        ("hwndOwner", wintypes.HWND),
        ("pidlRoot", ctypes.c_void_p),
        ("pszDisplayName", wintypes.LPWSTR),
        ("lpszTitle", wintypes.LPCWSTR),
        ("ulFlags", ctypes.c_uint),
        ("lpfn", ctypes.c_void_p),
        ("lParam", wintypes.LPARAM),
        ("iImage", ctypes.c_int),
    ]


def pick_folder(title: str, initial: str = "") -> str:
    """调系统原生的「选择文件夹」对话框。"""
    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        buf = ctypes.create_unicode_buffer(1024)
        bi = BROWSEINFOW()
        bi.hwndOwner = None
        bi.pszDisplayName = ctypes.cast(buf, wintypes.LPWSTR)
        bi.lpszTitle = title
        bi.ulFlags = 0x1 | 0x10 | 0x40        # 只选文件系统目录 + 可输入 + 新版样式
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return ""
        path = ctypes.create_unicode_buffer(1024)
        ok = shell32.SHGetPathFromIDListW(pidl, path)
        ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
        return path.value if ok else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- 检测
def is_server_dir(p: Path) -> bool:
    return (p / "server.properties").exists()


def detect_candidates() -> list:
    """安装包自己所在目录附近找服务端目录。"""
    app = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
    cands = []
    for c in (app, app.parent, app.parent.parent):
        if is_server_dir(c) and c not in cands:
            cands.append(c)
    # 兄弟目录（例如安装包放在某个盘符下，服务端就在它旁边的文件夹里）
    try:
        for c in app.parent.iterdir():
            if c.is_dir() and is_server_dir(c) and c not in cands:
                cands.append(c)
    except OSError:
        pass
    return cands[:3]


# ---------------------------------------------------------------- 快捷方式
def make_shortcut(lnk: Path, target: Path, workdir: Path):
    ps = (
        f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
        f'$s.TargetPath="{target}";'
        f'$s.WorkingDirectory="{workdir}";'
        f'$s.IconLocation="{target},0";'
        f'$s.Description="{APP_NAME} - 图形化控制你的 MC 服务器";'
        f'$s.Save()'
    )
    enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                   creationflags=NO_WINDOW, capture_output=True)


def shortcut_paths() -> list:
    """要创建的快捷方式：只有当前名字。"""
    home = Path(os.environ.get("USERPROFILE", "."))
    appdata = Path(os.environ.get("APPDATA", "."))
    return [
        home / "Desktop" / f"{APP_NAME}.lnk",
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk",
    ]


def legacy_shortcuts() -> list:
    """历史版本留下的快捷方式，升级时顺手清掉（只删不建）。"""
    home = Path(os.environ.get("USERPROFILE", "."))
    appdata = Path(os.environ.get("APPDATA", "."))
    return [
        home / "Desktop" / "Minecraft 控制面板.lnk",
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Minecraft 控制面板.lnk",
    ]


# ---------------------------------------------------------------- 安装
def do_install(server_dir: Path) -> tuple:
    panel = server_dir / "panel"
    panel.mkdir(parents=True, exist_ok=True)
    exe = panel / "MCPanel.exe"

    if not PAYLOAD.exists():
        return False, f"安装包损坏：找不到 {PAYLOAD.name}。请重新下载 Setup。"

    if exe.exists():
        try:                                  # 被占用说明面板正在跑
            with open(exe, "ab"):
                pass
        except OSError:
            return False, "面板正在运行，无法覆盖。\n\n请先在浏览器页面右上角点「退出面板」，再重新安装。"

    try:
        shutil.copy2(PAYLOAD, exe)
    except OSError as e:
        return False, f"复制文件失败：{e}\n\n（如果覆盖旧版失败，请先退出正在运行的面板）"

    for lnk in legacy_shortcuts():
        try:
            if lnk.exists():
                lnk.unlink()
        except OSError:
            pass

    for lnk in shortcut_paths():
        try:
            lnk.parent.mkdir(parents=True, exist_ok=True)
            make_shortcut(lnk, exe, panel)
        except Exception:
            pass

    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
            winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "MCServre")
            winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(panel))
            winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, str(exe))
            winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{exe}" --uninstall')
            winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD,
                              max(1, exe.stat().st_size // 1024))
    except Exception as e:
        return True, f"程序已安装，但写入卸载信息失败：{e}\n（不影响使用）"

    return True, ""


def looks_installed(server_dir: Path) -> bool:
    return (server_dir / "panel" / "MCPanel.exe").exists()


# ---------------------------------------------------------------- 流程
def gui() -> int:
    if not PAYLOAD.exists():
        msg(f"安装包不完整：缺少 {PAYLOAD.name}。\n\n请重新获取完整的 Setup 文件。",
            flags=0x10)
        return 2

    target = None
    for c in detect_candidates():
        r = msg(
            "检测到 Minecraft 服务端目录：\n\n"
            f"{c}\n\n"
            f"要装到这里吗？（会创建 {c.name}\\panel 子文件夹，"
            "不会改动存档、mod、配置）\n\n"
            "选「否」可以自己指定目录。",
            flags=0x23,   # 是否取消
        )
        if r == 6:
            target = c
            break
        if r == 2:
            return 1

    while target is None:
        p = pick_folder("请选择你的 Minecraft 服务端目录（包含 server.properties 的那一层）")
        if not p:
            if msg("已取消安装。", flags=0x30) == 1:
                return 1
            continue
        cand = Path(p)
        if not is_server_dir(cand):
            r = msg(
                f"这个目录里没有 server.properties：\n\n{cand}\n\n"
                "面板需要靠它找到 Java、mods 和存档。\n\n"
                "要重新选择吗？（选「否」则退出安装）",
                flags=0x24,
            )
            if r != 6:
                return 1
            continue
        target = cand

    if looks_installed(target):
        r = msg(
            f"这里已经装过控制面板了：\n\n{target / 'panel'}\n\n"
            "继续安装会覆盖程序本体（保存的备份 zip 不会被动）。\n\n确定继续？",
            flags=0x24,
        )
        if r != 6:
            return 1

    ok, err = do_install(target)
    if not ok:
        msg(err, flags=0x10)
        return 2

    exe = target / "panel" / "MCPanel.exe"
    note = f"\n\n注意：{err}" if err else ""
    has_forge = (target / "libraries" / "net" / "minecraftforge" / "forge").is_dir() \
        or any(target.glob("forge-*.jar"))

    if not has_forge:
        r = msg(
            "安装完成。\n\n"
            f"安装位置：{target / 'panel'}\n"
            "桌面和开始菜单已创建快捷方式。\n\n"
            "这个目录里还没有装 Forge。\n"
            "要现在打开面板，选择你要用的 Minecraft / Forge 版本并一键下载安装吗？\n\n"
            "（选「否」也可以，之后从「服务器设置 → Forge 版本」里随时安装）"
            f"{note}",
            flags=0x24,
        )
        args = [str(exe), "--choose-forge"] if r == 6 else None
    else:
        r = msg(
            "安装完成。\n\n"
            f"安装位置：{target / 'panel'}\n"
            "桌面和开始菜单已创建快捷方式。\n"
            f"以后双击「{APP_NAME}」就能开服、看日志、管玩家、备份存档。"
            f"{note}\n\n要现在启动面板吗？",
            flags=0x24,
        )
        args = [str(exe)] if r == 6 else None

    if args:
        try:
            subprocess.Popen(args, cwd=str(exe.parent))
        except Exception as e:
            msg(f"启动失败：{e}\n\n请手动双击 {exe}", flags=0x10)
    return 0


def silent(argv) -> int:
    target = None
    for a in argv:
        if a.startswith("--dir="):
            target = Path(a.split("=", 1)[1].strip('"'))
    if not target:
        print("silent 模式需要 --dir=<服务端目录>")
        return 2
    ok, err = do_install(target)
    print("OK" if ok else "FAIL: " + err)
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        if "--silent" in sys.argv:
            sys.exit(silent(sys.argv))
        sys.exit(gui())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            (Path(tempfile.gettempdir()) / "mcpanel-setup-error.log").write_text(tb, encoding="utf-8")
        except Exception:
            pass
        msg(f"安装程序出错：\n\n{tb[-1000:]}", flags=0x10)
        sys.exit(2)
