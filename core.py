#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minecraft 服务端控制台 —— 后端核心（Qt 界面调用这一层）
纯 Python 标准库，无第三方依赖。仅监听 127.0.0.1，不对外暴露。

设计要点：
  1. 停止服务器一律走 stdin 发送 stop，等存档落盘，绝不强杀；
  2. 备份在服务器运行中会先 save-off + save-all flush，备份完再 save-on；
  3. 面板进程退出时，若服务器还在跑，先优雅停服再退出。
"""

import atexit
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from collections import deque
from pathlib import Path

# ---------------------------------------------------------------- 路径解析
FROZEN = getattr(sys, "frozen", False)


def _app_dir() -> Path:
    """程序自身所在目录：exe 所在目录，或 panel.py 所在目录。"""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _res_dir() -> Path:
    """只读资源目录（打包后 index.html 会被解到 _MEIPASS）。"""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", _app_dir()))
    return Path(__file__).resolve().parent


def _find_base(app: Path) -> Path:
    """
    服务端根目录 = 含 server.properties 的那一级。
    这样面板既可以直接放在服务端根目录，也可以放在任意子目录（如 panel\\）。
    """
    for c in (app, app.parent):
        if (c / "server.properties").exists():
            return c
    p = app
    for _ in range(3):
        p = p.parent
        if (p / "server.properties").exists():
            return p
    return app.parent


PANEL_DIR = _app_dir()                                  # 备份 / 面板日志存放处
BASE = _find_base(PANEL_DIR)                            # 服务端根目录（向上找 server.properties）
BACKUP_DIR = PANEL_DIR / "backups"
LOG_DIR = PANEL_DIR / "logs"
WORLD_DIR = BASE / "world"
MODS_DIR = BASE / "mods"
MODS_DISABLED = BASE / "mods-disabled"
PROPS = BASE / "server.properties"
JVM_ARGS = BASE / "user_jvm_args.txt"
WHITELIST = BASE / "whitelist.json"
OPS = BASE / "ops.json"
BANNED = BASE / "banned-players.json"
def _find_java() -> Path:
    """
    Java 位置，按优先级：
      1) 服务端目录下的 runtime/bin/java（Forge 安装器自带的那种）
      2) 环境变量 JAVA_HOME
      3) PATH 里的 java
    都找不到就返回第 1 个候选，报错时能看到期望路径。
    """
    exe = "java.exe" if os.name == "nt" else "java"
    local = BASE / "runtime" / "bin" / exe
    if local.exists():
        return local
    jh = os.environ.get("JAVA_HOME")
    if jh:
        c = Path(jh) / "bin" / exe
        if c.exists():
            return c
    found = shutil.which("java")
    return Path(found) if found else local


JAVA = _find_java()


for d in (BACKUP_DIR, LOG_DIR, MODS_DISABLED):
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- 工具函数
def detect_forge() -> dict:
    """
    检测服务端目录里的 Forge：
      kind="win_args"  1.17+ 官方安装器生成的方式（libraries/.../win_args.txt）
      kind="jar"       1.16.5 及更早，直接用 forge-*.jar 启动
      kind=None        还没装
    """
    lib = BASE / "libraries" / "net" / "minecraftforge" / "forge"
    if lib.is_dir():
        dirs = [d for d in lib.iterdir() if d.is_dir() and (d / "win_args.txt").exists()]
        if dirs:
            d = max(dirs, key=lambda x: x.name)
            mc, _, ver = d.name.partition("-")
            return {"kind": "win_args", "name": d.name, "mc": mc, "forge": ver,
                    "args": f"libraries/net/minecraftforge/forge/{d.name}/win_args.txt",
                    "jar": ""}
    for pat in ("forge-*-universal.jar", "forge-*.jar"):
        for jar in sorted(BASE.glob(pat), reverse=True):
            if "installer" in jar.name.lower():
                continue
            parts = jar.name[:-4].split("-")        # forge-1.16.5-36.2.34
            return {"kind": "jar", "name": jar.name,
                    "mc": parts[1] if len(parts) > 1 else "",
                    "forge": parts[2] if len(parts) > 2 else "",
                    "args": "", "jar": jar.name}
    return {"kind": None, "name": "", "mc": "", "forge": "", "args": "", "jar": ""}


FORGE = detect_forge()
FORGE_ARGS = FORGE["args"]

NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def offline_uuid(name: str) -> str:
    """离线模式 UUID：MD5('OfflinePlayer:<name>') 并置版本/变体位，与 Minecraft 一致。"""
    d = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest())
    d[6] = (d[6] & 0x0F) | 0x30
    d[8] = (d[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(d)))


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------- Win32 小工具
def msgbox(text: str, title: str = "Minecraft 控制面板", flags: int = 0x40) -> int:
    """flags: 0x40 信息 / 0x30 警告 / 0x10 错误；返回 MessageBox 的按钮值。"""
    try:
        import ctypes
        return int(ctypes.windll.user32.MessageBoxW(None, text, title, flags))
    except Exception:
        print(text)
        return 1


# ---------------------------------------------------------------- 单实例
_INSTANCE_HANDLE = None


def claim_single_instance(name: str = "MCServre.Panel.Qt.v1") -> bool:
    """
    用命名互斥量判断是否已有面板在运行。第一个进程拿到锁返回 True，
    后来的进程返回 False（界面据此提示「已经在运行了」）。
    句柄挂在模块级变量上，进程退出时由系统回收。
    """
    global _INSTANCE_HANDLE
    if os.name != "nt":
        return True
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        h = k32.CreateMutexW(None, False, name)
        if not h or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            return False
        _INSTANCE_HANDLE = h
        return True
    except Exception:
        return True


def dir_size(p: Path) -> int:
    total = 0
    try:
        for root, _, files in os.walk(p):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
    except OSError:
        pass
    return total


# ------------------------------------------------------------ 孤儿进程防护
def make_job_object():
    """
    Windows 作业对象 + KILL_ON_JOB_CLOSE：
    面板窗口被直接叉掉（进程被硬杀）时，JDK 进程会被系统一并结束，
    不会留下一个「还在跑但没人管」的孤儿服。
    正常关服请用面板上的「保存并关闭」或「退出面板」。
    """
    if os.name != "nt":
        return None
    import ctypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class EXT_LIMIT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMIT),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        h = k32.CreateJobObjectW(None, None)
        if not h:
            return None
        info = EXT_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x2000   # KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None
        return (k32, h)
    except Exception:
        return None


JOB = make_job_object()


# ---------------------------------------------------------------- 进程管理
class Server:
    """服务端进程 + 日志缓冲 + 状态机。"""

    def __init__(self):
        self.lock = threading.RLock()
        self.proc = None
        self.state = "stopped"          # stopped / starting / running / stopping
        self.pid = None
        self.started_at = None
        self.stopped_at = None
        self.exit_code = None
        self.lines = deque(maxlen=6000)
        self.seq = 0
        self.players = {}               # name -> 加入时间
        self.last_error = ""
        self._stop_requested = False
        self._reader = None

    # ---- 日志
    # 无害噪音：mod 联网查版本失败、玩家手误输入等都常见，不该标红吓人
    BENIGN = (
        "VersionChecker", "Forge Version Check", "update information",
        "SSLHandshakeException", "ConnectException", "Connection reset",
        "HTTP connect timed out", "Unknown or incomplete command",
        "moved too quickly", "moved wrongly", "Read timed out",
    )

    TRACE_RE = re.compile(r"^(\s+at |Caused by:|\.\.\. \d+ more|Suppressed:)")

    def push(self, text: str, raw: str = ""):
        with self.lock:
            self.seq += 1
            level = "info"
            up = raw.upper()
            benign = any(k.upper() in up for k in self.BENIGN)
            if "/ERROR" in up or "EXCEPTION" in up or "FATAL" in up:
                level = "warn" if benign else "error"
            elif "/WARN" in up:
                level = "warn"
            elif "DONE (" in up:
                level = "ok"
                self.last_error = ""
            if self.TRACE_RE.match(text):
                level = "trace"           # Java 栈追踪：默认折叠，需要时再展开
            self.lines.append(
                {"seq": self.seq, "t": time.strftime("%H:%M:%S"), "text": text, "level": level}
            )
            if level == "error":
                self.last_error = text

    def log_file(self, line: str):
        try:
            with open(LOG_DIR / "panel.log", "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {line}\n")
        except OSError:
            pass

    # ---- 启动
    def start(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return False, "服务器已经在运行中"
            if not JAVA.exists():
                return False, f"找不到 Java：{JAVA}"
            info = detect_forge()
            if info["kind"] == "win_args":
                cmd = [str(JAVA), "@user_jvm_args.txt", f"@{info['args']}", "nogui"]
            elif info["kind"] == "jar":
                cmd = [str(JAVA), "@user_jvm_args.txt", "-jar", info["jar"], "nogui"]
            else:
                return False, "这个目录里没检测到 Forge。请先到「服务器设置 → Forge 版本」里下载安装。"
            flags = 0
            if os.name == "nt":
                # CREATE_NEW_PROCESS_GROUP: 避免 Ctrl+C 连带；CREATE_NO_WINDOW: 不弹出黑色命令行窗口
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
            try:
                self.proc = subprocess.Popen(
                    cmd, cwd=str(BASE), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, bufsize=-1, creationflags=flags,
                )
            except Exception as e:
                self.state = "stopped"
                return False, f"启动失败：{e}"
            self.pid = self.proc.pid
            if JOB:
                try:
                    k32, hjob = JOB
                    if not k32.AssignProcessToJobObject(hjob, int(self.proc._handle)):
                        self.log_file("作业对象绑定失败（不影响使用，但面板被硬杀时可能残留 Java 进程）")
                except Exception as e:
                    self.log_file(f"作业对象绑定异常 {e}")
            self.state = "starting"
            self.started_at = time.time()
            self.stopped_at = None
            self.exit_code = None
            self.players.clear()
            self._stop_requested = False
            self.push(f"[面板] 正在启动服务器，PID {self.pid} …", "[panel/INFO]")
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            return True, "已发送启动指令，等待 Done 出现"

    # ---- 读日志
    def _read_loop(self):
        proc = self.proc
        while True:
            try:
                raw = proc.stdout.readline()
            except (ValueError, OSError):
                break
            if not raw:
                break
            if isinstance(raw, bytes):
                for enc in ("utf-8", "gbk", "latin-1"):
                    try:
                        s = raw.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    s = raw.decode("utf-8", "replace")
            else:
                s = raw
            s = s.rstrip("\r\n")
            if not s:
                continue
            self._analyse(s)
            self.push(s, s)
        # 进程结束
        code = proc.poll()
        if code is None:
            try:
                code = proc.wait(timeout=10)
            except Exception:
                code = -1
        with self.lock:
            self.exit_code = code
            if self.state != "stopped":
                self.state = "stopped"
            self.stopped_at = time.time()
            self.pid = None
            self.players.clear()
            ok = "正常退出" if code == 0 else f"异常退出（退出码 {code}）"
            self.push(f"[面板] 服务器已停止，{ok}", "[panel/INFO]")

    def _analyse(self, s: str):
        with self.lock:
            if "Done (" in s and "For help" in s:
                self.state = "running"
                self.started_at = self.started_at or time.time()
            if "Stopping the server" in s:
                self.state = "stopping"
            m = re.search(r"\]: ([A-Za-z0-9_]{1,16}) joined the game", s)
            if m:
                self.players[m.group(1)] = time.time()
            m = re.search(r"\]: ([A-Za-z0-9_]{1,16}) left the game", s)
            if m:
                self.players.pop(m.group(1), None)
            if "You need to agree to the EULA" in s:
                self.last_error = "需要同意 EULA：请把 eula.txt 里的 eula=false 改成 true"
            if "Address already in use" in s:
                self.last_error = "端口被占用：可能已经有一个服务器在跑"

    # ---- 发命令
    def command(self, cmd: str):
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                return False, "服务器没在运行"
            if not cmd.strip():
                return False, "命令为空"
            try:
                self.proc.stdin.write((cmd.strip() + "\n").encode("utf-8"))
                self.proc.stdin.flush()
            except Exception as e:
                return False, f"写入失败：{e}"
            self.push(f"> {cmd.strip()}", "[panel/INFO]")
            return True, "已发送"

    # ---- 停止
    def stop(self, force=False):
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                return False, "服务器没在运行"
            if force:
                try:
                    self.proc.kill()
                except Exception as e:
                    return False, f"强杀失败：{e}"
                self.push("[面板] 已强制结束进程（存档可能未完整保存）", "[panel/WARN]")
                return True, "已强杀"
            if self._stop_requested:
                return False, "已经在停止了，请稍候"
            self._stop_requested = True
            self.state = "stopping"
        ok, msg = self.command("stop")
        if not ok:
            self._stop_requested = False
            return False, msg
        threading.Thread(target=self._watch_stop, daemon=True).start()
        return True, "正在保存存档并关闭，请勿关闭面板"

    def _watch_stop(self):
        try:
            if self.proc:
                self.proc.wait(timeout=180)
        except Exception:
            self.push("[面板] 停止超时（超过 180 秒），可考虑强制结束", "[panel/WARN]")

    # ---- 状态
    def status(self):
        with self.lock:
            running = bool(self.proc and self.proc.poll() is None)
            up = int(time.time() - self.started_at) if (running and self.started_at) else 0
            fg = detect_forge()
            return {
                "state": self.state if running else "stopped",
                "running": running,
                "pid": self.pid,
                "uptime": up,
                "uptime_text": fmt_duration(up),
                "online": sorted(self.players.keys()),
                "online_count": len(self.players),
                "last_error": self.last_error,
                "exit_code": self.exit_code,
                "java": str(JAVA),
                "forge": fg,
                "forge_args": fg["args"],
            }


def fmt_duration(sec: int) -> str:
    if sec <= 0:
        return "-"
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    if h:
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分 {s} 秒"
    return f"{s} 秒"


SRV = Server()


# ---------------------------------------------------------------- 备份
class Backup:
    def __init__(self):
        self.lock = threading.Lock()
        self.job = {"running": False, "progress": 0, "total": 0, "file": "", "error": "", "message": ""}

    def list(self):
        items = []
        for p in sorted(BACKUP_DIR.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
            st = p.stat()
            items.append({
                "name": p.name,
                "size": st.st_size,
                "size_text": human_size(st.st_size),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                "mtime": st.st_mtime,
            })
        return items

    def start(self, note: str = ""):
        with self.lock:
            if self.job["running"]:
                return False, "已有备份正在进行中"
            self.job = {"running": True, "progress": 0, "total": 0, "file": "", "error": "", "message": "准备中"}
        threading.Thread(target=self._run, args=(note,), daemon=True).start()
        return True, "备份已开始"

    def _run(self, note: str):
        hot = SRV.status()["running"]
        name = "world-" + time.strftime("%Y%m%d-%H%M%S") + ".zip"
        out = BACKUP_DIR / name
        saved_off = False
        try:
            if hot:
                self.job["message"] = "暂停自动保存并刷新存档……"
                ok, _ = SRV.command("save-off")
                SRV.command("save-all flush")
                saved_off = ok
                time.sleep(6)                       # 等 region 文件落盘
            files = []
            for root, _, fns in os.walk(WORLD_DIR):
                for fn in fns:
                    files.append(os.path.join(root, fn))
            self.job["total"] = len(files)
            self.job["message"] = f"压缩 {len(files)} 个文件"
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
                for i, fp in enumerate(files, 1):
                    try:
                        z.write(fp, os.path.relpath(fp, WORLD_DIR.parent))
                    except OSError:
                        pass
                    if i % 40 == 0 or i == len(files):
                        self.job["progress"] = i
            size = out.stat().st_size
            self.job["file"] = name
            self.job["message"] = f"完成：{name}（{human_size(size)}）"
            SRV.log_file(f"备份完成 {name} {human_size(size)} {note}")
        except Exception as e:
            self.job["error"] = str(e)
            self.job["message"] = f"备份失败：{e}"
            if out.exists():
                try:
                    out.unlink()
                except OSError:
                    pass
        finally:
            if saved_off:
                SRV.command("save-on")
            self.job["running"] = False
            self.job["progress"] = self.job["total"]

    def delete(self, name: str):
        if not re.match(r"^world-[\w\-]+\.zip$", name):
            return False, "文件名不合法"
        p = BACKUP_DIR / name
        if not p.exists():
            return False, "文件不存在"
        try:
            p.unlink()
            return True, "已删除"
        except OSError as e:
            return False, f"删除失败：{e}"


BK = Backup()


class AutoBackup:
    """面板内定时备份：只在服务器运行且无进行中备份时触发。"""

    def __init__(self):
        self.enabled = False
        self.interval_h = 6.0
        self.last = 0.0
        self._t = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._t.start()

    def _loop(self):
        while True:
            time.sleep(60)
            try:
                if not self.enabled:
                    continue
                if time.time() - self.last < self.interval_h * 3600:
                    continue
                if not SRV.status()["running"] or BK.job["running"]:
                    continue
                self.last = time.time()
                SRV.log_file(f"触发自动备份（每 {self.interval_h} 小时）")
                BK.start("auto")
            except Exception as e:
                SRV.log_file(f"自动备份异常 {e}")


AUTO = AutoBackup()


# ---------------------------------------------------------------- server.properties
PROP_SCHEMA = [
    ("motd", "服务器描述（MOTD）", "text"),
    ("max-players", "最大人数", "number"),
    ("difficulty", "难度", "select:peaceful,easy,normal,hard"),
    ("gamemode", "默认游戏模式", "select:survival,creative,adventure,spectator"),
    ("view-distance", "视距（区块）", "number"),
    ("simulation-distance", "模拟距离", "number"),
    ("online-mode", "正版验证", "bool"),
    ("white-list", "开启白名单", "bool"),
    ("pvp", "允许 PVP", "bool"),
    ("allow-flight", "允许飞行", "bool"),
    ("allow-nether", "允许下界", "bool"),
    ("enable-command-block", "允许命令方块", "bool"),
    ("spawn-protection", "出生点保护半径", "number"),
    ("player-idle-timeout", "挂机踢出（分钟，0=不踢）", "number"),
    ("server-port", "端口（改完需重启）", "number"),
]


def read_props() -> dict:
    data = {}
    try:
        raw = PROPS.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return data
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def write_props(updates: dict):
    try:
        raw = PROPS.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw = "#Minecraft server properties\n"
    lines = raw.splitlines()
    seen = set()
    for i, line in enumerate(lines):
        if line.strip().startswith("#") or "=" not in line:
            continue
        k = line.split("=", 1)[0].strip()
        if k in updates:
            lines[i] = f"{k}={updates[k]}"
            seen.add(k)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    PROPS.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- JVM 参数
def read_jvm():
    txt = JVM_ARGS.read_text(encoding="utf-8", errors="replace") if JVM_ARGS.exists() else ""
    xms = re.search(r"^-Xms(\d+)([GgMm])", txt, re.M)
    xmx = re.search(r"^-Xmx(\d+)([GgMm])", txt, re.M)
    def to_mb(m):
        if not m:
            return None
        n = int(m.group(1))
        return n * 1024 if m.group(2).lower() == "g" else n
    return {"xms_mb": to_mb(xms), "xmx_mb": to_mb(xmx)}


def write_jvm(xms_mb: int, xmx_mb: int):
    if not (512 <= xms_mb <= 65536 and 512 <= xmx_mb <= 65536):
        return False, "内存值超出允许范围（512MB - 64GB）"
    if xms_mb > xmx_mb:
        return False, "初始内存不能大于最大内存"
    try:
        lines = JVM_ARGS.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    out, has_xms, has_xmx = [], False, False
    for line in lines:
        s = line.strip()
        if s.startswith("-Xms"):
            out.append(f"-Xms{xms_mb}M"); has_xms = True
        elif s.startswith("-Xmx"):
            out.append(f"-Xmx{xmx_mb}M"); has_xmx = True
        else:
            out.append(line)
    if not has_xms:
        out.insert(0, f"-Xms{xms_mb}M")
    if not has_xmx:
        out.insert(1, f"-Xmx{xmx_mb}M")
    JVM_ARGS.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True, "已保存，重启服务器后生效"


# ---------------------------------------------------------------- Mod 管理
def list_mods():
    def scan(d: Path, enabled: bool):
        out = []
        if d.is_dir():
            for p in sorted(d.glob("*.jar"), key=lambda x: x.name.lower()):
                st = p.stat()
                out.append({
                    "name": p.name, "enabled": enabled,
                    "size": st.st_size, "size_text": human_size(st.st_size),
                    "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                })
        return out
    return scan(MODS_DIR, True) + scan(MODS_DISABLED, False)


def toggle_mod(name: str, enable: bool):
    if "/" in name or "\\" in name or not name.endswith(".jar"):
        return False, "文件名不合法"
    src = (MODS_DISABLED if enable else MODS_DIR) / name
    dst = (MODS_DIR if enable else MODS_DISABLED) / name
    if not src.exists():
        return False, "文件不存在，可能已被移动"
    try:
        shutil.move(str(src), str(dst))
    except OSError as e:
        return False, f"移动失败：{e}"
    return True, ("已启用，重启后生效" if enable else "已禁用，重启后生效")


# ---------------------------------------------------------------- 玩家 / 白名单 / 黑名单
def get_players():
    wl = read_json(WHITELIST, [])
    ops = read_json(OPS, [])
    ban = read_json(BANNED, [])
    opmap = {o.get("name", ""): o.get("level", 0) for o in ops if isinstance(o, dict)}
    return {
        "online": SRV.status()["online"],
        "whitelist": [{"name": w.get("name", ""), "uuid": w.get("uuid", "")} for w in wl if isinstance(w, dict)],
        "banned": [{"name": b.get("name", ""), "reason": b.get("reason", "")} for b in ban if isinstance(b, dict)],
        "ops": [{"name": n, "level": lv} for n, lv in opmap.items()],
        "mode": "whitelist" if read_props().get("white-list") == "true" else "blacklist",
    }


def set_access_mode(mode: str):
    """white = 白名单模式（只放行名单内）；否则黑名单模式（封禁者除外，其余都能进）。"""
    white = "true" if mode == "whitelist" else "false"
    write_props({"white-list": white})
    if SRV.status()["running"]:
        SRV.command("whitelist on" if mode == "whitelist" else "whitelist off")
    return True


def _now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S +0800")


def ban_add(name: str, reason: str = "管理员封禁"):
    if not NAME_RE.match(name):
        return False, "玩家名只能是 1-16 位字母、数字、下划线"
    if SRV.status()["running"]:
        ok, msg = SRV.command(f"ban {name} {reason}".strip())
        return ok, ("已封禁（在线的话会被立刻踢出）" if ok else msg)
    data = read_json(BANNED, [])
    if any(b.get("name", "").lower() == name.lower() for b in data if isinstance(b, dict)):
        return False, f"{name} 已经在黑名单里了"
    data.append({"uuid": offline_uuid(name), "name": name,
                 "created": _now_iso(), "source": "MCPanel",
                 "expires": "forever", "reason": reason})
    write_json(BANNED, data)
    return True, "已写入黑名单（离线 UUID）"


def ban_remove(name: str):
    if SRV.status()["running"]:
        ok, msg = SRV.command(f"pardon {name}")
        return ok, ("已解除封禁" if ok else msg)
    data = read_json(BANNED, [])
    new = [b for b in data if b.get("name", "").lower() != name.lower()]
    if len(new) == len(data):
        return False, f"黑名单里没有 {name}"
    write_json(BANNED, new)
    return True, "已移出黑名单"


def whitelist_add(name: str):
    if not NAME_RE.match(name):
        return False, "玩家名只能是 1-16 位字母、数字、下划线"
    wl = read_json(WHITELIST, [])
    if any(w.get("name", "").lower() == name.lower() for w in wl if isinstance(w, dict)):
        return False, f"{name} 已经在白名单里了"
    if SRV.status()["running"]:
        ok, msg = SRV.command(f"whitelist add {name}")
        if ok:
            SRV.command("whitelist reload")
        return ok, ("已通过游戏命令加入白名单" if ok else msg)
    wl.append({"uuid": offline_uuid(name), "name": name})
    write_json(WHITELIST, wl)
    return True, "已写入白名单文件（离线 UUID）"


def whitelist_remove(name: str):
    if SRV.status()["running"]:
        ok, msg = SRV.command(f"whitelist remove {name}")
        if ok:
            SRV.command("whitelist reload")
        return ok, ("已通过游戏命令移出白名单" if ok else msg)
    wl = read_json(WHITELIST, [])
    new = [w for w in wl if w.get("name", "").lower() != name.lower()]
    if len(new) == len(wl):
        return False, f"白名单里没有 {name}"
    write_json(WHITELIST, new)
    return True, "已移出白名单"


def set_op(name: str, enable: bool):
    if not NAME_RE.match(name):
        return False, "玩家名不合法"
    if SRV.status()["running"]:
        ok, msg = SRV.command(("op " if enable else "deop ") + name)
        return ok, (msg if ok else msg)
    ops = read_json(OPS, [])
    ops = [o for o in ops if o.get("name", "").lower() != name.lower()]
    if enable:
        ops.append({"uuid": offline_uuid(name), "name": name, "level": 4,
                    "bypassesPlayerLimit": False})
    write_json(OPS, ops)
    return True, ("已设为 OP（离线 UUID）" if enable else "已取消 OP")


def cleanup():
    try:
        if SRV.status()["running"]:
            SRV.log_file("面板被关闭，尝试优雅停服")
            SRV.stop()
            for _ in range(60):
                time.sleep(1)
                if not SRV.status()["running"]:
                    break
    except Exception:
        pass


atexit.register(cleanup)


# ---------------------------------------------------------------- 卸载
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPanel"


def _shortcuts():
    home = Path(os.environ.get("USERPROFILE", "."))
    appdata = Path(os.environ.get("APPDATA", "."))
    out = []
    # 新旧两个名字都清，升级过来的用户不会留下废快捷方式
    for name in ("Minecraft 控制台", "Minecraft 控制面板"):
        out.append(home / "Desktop" / f"{name}.lnk")
        out.append(appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{name}.lnk")
    return out


def _panel_alive() -> bool:
    """已经有进程持着单实例锁，说明面板还在跑。"""
    return not claim_single_instance()


def launch_uninstaller():
    """从 exe 里启动卸载：复制自身到临时目录再跑，避免删不掉正在运行的自己。"""
    if not FROZEN:
        run_uninstall(_app_dir())
        return
    import tempfile
    tmp = Path(tempfile.gettempdir()) / f"mcpanel-uninst-{os.getpid()}.exe"
    try:
        shutil.copy2(sys.executable, tmp)
        subprocess.Popen([str(tmp), "--uninstall-run", str(_app_dir())],
                         creationflags=0x08000000)
    except Exception as e:
        msgbox(f"无法启动卸载程序：\n{e}", flags=0x10)
    sys.exit(0)


def _self_delete():
    if not FROZEN:
        return
    try:
        subprocess.Popen(f'cmd /c timeout /t 2 >nul & del /f /q "{sys.executable}"',
                         shell=True, creationflags=0x08000000)
    except Exception:
        pass


def run_uninstall(target: Path, silent: bool = False, keep_backups: bool = True):
    if not silent:
        if _panel_alive():
            msgbox("控制面板还在运行。\n\n请先关掉面板窗口（点右上角关闭，或在「服务器」页点「退出面板」），"
                   "再重新卸载。", flags=0x30)
            return
        if msgbox(f"确定要卸载 Minecraft 控制面板吗？\n\n安装位置：{target}\n\n"
                  "只删除面板程序本身，不会动 world 存档、mods、config、server.properties。",
                  "卸载 Minecraft 控制面板", 0x24) != 6:
            return
        keep = msgbox("是否保留已经备份的存档（panel\\backups 里的 zip 文件）？\n\n建议选「是」。",
                      "卸载 Minecraft 控制面板", 0x24) == 6
    else:
        keep = keep_backups

    removed, failed = 0, []
    skip = {"backups"} if keep else set()
    if target.is_dir():
        for p in list(target.iterdir()):
            if p.name.lower() in skip:
                continue
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                removed += 1
            except OSError as e:
                failed.append(f"{p.name}（{e.__class__.__name__}）")
    if not keep:
        try:
            target.rmdir()
        except OSError:
            pass

    for lnk in _shortcuts():
        try:
            if lnk.exists():
                lnk.unlink()
        except OSError:
            pass
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
    except Exception:
        pass

    if silent:
        print(f"UNINSTALL_OK removed={removed} failed={len(failed)} keep_backups={keep}")
        return

    msg = f"已删除 {removed} 项。"
    if failed:
        msg += "\n\n以下文件被占用，请重启电脑后手动删除：\n" + "\n".join(failed[:6])
    msg += "\n\n桌面与开始菜单快捷方式、控制面板里的卸载项都已清除。"
    if keep:
        msg += f"\n\n备份已保留在：{target / 'backups'}"
    msgbox(msg, "卸载完成")
    _self_delete()


def open_folder(target: str = "base"):
    """在资源管理器里打开指定目录。"""
    p = {
        "base": BASE, "backups": BACKUP_DIR, "mods": MODS_DIR,
        "world": WORLD_DIR, "logs": BASE / "logs", "panel": PANEL_DIR,
    }.get(target, BASE)
    try:
        if os.name == "nt":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return True
    except Exception:
        return False


def handle_uninstall_args(argv) -> bool:
    """安装/卸载入口：返回 True 表示参数已被卸载流程消费，调用方应直接退出。"""
    if "--uninstall" in argv:
        launch_uninstaller()
        return True
    if "--uninstall-run" in argv:
        i = argv.index("--uninstall-run")
        run_uninstall(
            Path(argv[i + 1]) if len(argv) > i + 1 else _app_dir(),
            silent="--yes" in argv,
            keep_backups="--drop-backups" not in argv,
        )
        return True
    return False


# ---------------------------------------------------------------- Forge 版本管理
FORGE_MIRROR = "https://bmclapi2.bangbang93.com"     # 国内镜像，先试它
FORGE_MAVEN = "https://maven.minecraftforge.net"     # 官方源，镜像挂了再试
PROMOS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
# 安装器支持 --mirror；官方 maven 在国内经常拉一半断掉，默认走 BMCLAPI
MAVEN_MIRRORS = {
    "bmcl": "https://bmclapi2.bangbang93.com/maven/",
    "official": "",          # 空 = 不传 --mirror，走官方源
}
CACHE_DIR = PANEL_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _http_json(url: str, timeout: int = 20, retries: int = 2):
    """抓 JSON；网络偶发失败重试两次。"""
    import urllib.request
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "MCPanel/1.1 (+https://github.com/)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            if i < retries:
                time.sleep(1.2)
    raise last


def _ver_tuple(v: str) -> tuple:
    out = []
    for p in str(v).replace("_pre", ".").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(-1)
    return tuple(out)


def _cached_json(name: str, url: str, ttl: int = 3600, force: bool = False):
    p = CACHE_DIR / name
    if not force and p.exists() and time.time() - p.stat().st_mtime < ttl:
        data = read_json(p, None)
        if data:
            return data
    data = _http_json(url)
    write_json(p, data)
    return data


def list_mc_versions(force: bool = False) -> list:
    """有 Forge 构建的 Minecraft 版本，从新到旧。"""
    data = _cached_json("forge_mc.json", f"{FORGE_MIRROR}/forge/minecraft", 86400, force) or []
    return sorted([v for v in data if isinstance(v, str)], key=_ver_tuple, reverse=True)


def list_forge_builds(mc: str, force: bool = False) -> list:
    """某个 MC 版本下的 Forge 构建号，从新到旧。"""
    name = f"forge_{mc.replace('.', '_')}.json"
    data = _cached_json(name, f"{FORGE_MIRROR}/forge/minecraft/{mc}", 3600, force) or []
    vers = {b.get("version", "") for b in data if isinstance(b, dict)}
    vers.discard("")
    return sorted(vers, key=_ver_tuple, reverse=True)


def forge_promos(force: bool = False) -> dict:
    """官方推荐的 recommended / latest 版本号。"""
    try:
        d = _cached_json("forge_promos.json", PROMOS_URL, 3600, force) or {}
        return d.get("promos", {}) if isinstance(d, dict) else {}
    except Exception:
        return {}


def forge_installer_urls(mc: str, ver: str) -> list:
    name = f"forge-{mc}-{ver}-installer.jar"
    path = f"net/minecraftforge/forge/{mc}-{ver}/{name}"
    return [f"{FORGE_MIRROR}/maven/{path}", f"{FORGE_MAVEN}/{path}"]


def java_version(path=None):
    """返回 (主版本号, 版本首行)。1.8 → 8，17.0.20 → 17。"""
    exe = str(path or JAVA)
    flags = 0x08000000 if os.name == "nt" else 0
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, text=True,
                           errors="replace", timeout=20, creationflags=flags)
    except Exception as e:
        return 0, f"运行 Java 失败：{e}"
    txt = (r.stderr or "") + (r.stdout or "")
    line = next((l.strip() for l in txt.splitlines() if l.strip()), "")
    m = re.search(r'version "(\d+)(?:\.(\d+))?', txt)
    if not m:
        return 0, line or "无法识别"
    major = int(m.group(1))
    if major == 1:
        major = int(m.group(2) or 0)
    return major, line


def required_java(mc: str) -> int:
    v = _ver_tuple(mc)
    if v >= (1, 20, 5):
        return 21
    if v >= (1, 18):
        return 17
    if v >= (1, 17):
        return 16
    return 8


class ForgeInstall:
    """下载并安装 Forge；进度和日志放在 job 字典里供界面轮询。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.job = {"running": False, "phase": "", "percent": 0,
                    "message": "", "error": "", "lines": []}

    def log(self, text: str):
        with self.lock:
            self.job["lines"].append(text)
            if len(self.job["lines"]) > 400:
                del self.job["lines"][:-400]

    def start(self, mc: str, ver: str, source: str = "bmcl"):
        with self.lock:
            if self.job["running"]:
                return False, "已经有安装任务在进行中"
            if SRV.status()["running"]:
                return False, "服务器正在运行，请先「停止」再安装 Forge"
            self.job = {"running": True, "phase": "准备", "percent": 0,
                        "message": "准备下载…", "error": "", "lines": []}
        threading.Thread(target=self._run, args=(mc, ver, source), daemon=True).start()
        return True, "开始安装"

    def _download(self, mc, ver, dest: Path):
        import urllib.request
        self.job["phase"] = "下载"
        last = ""
        for url in forge_installer_urls(mc, ver):
            try:
                self.log(f"下载：{url}")
                req = urllib.request.Request(url, headers={"User-Agent": "MCPanel/1.1"})
                with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                    total = int(r.headers.get("Content-Length") or 0)
                    done = 0
                    while True:
                        chunk = r.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            self.job["percent"] = min(40, 5 + int(done * 35 / total))
                            self.job["message"] = \
                                f"下载安装器 {done // 1024} / {total // 1024} KB"
                if dest.stat().st_size > 1024 * 512:
                    self.job["percent"] = 40
                    self.log(f"下载完成：{dest.name}（{human_size(dest.stat().st_size)}）")
                    return
                raise RuntimeError("文件太小，可能不是安装器")
            except Exception as e:
                last = f"{url} → {e}"
                self.log(f"失败：{last}")
                if dest.exists():
                    try:
                        dest.unlink()
                    except OSError:
                        pass
        raise RuntimeError(f"下载失败：{last}")

    def _run(self, mc: str, ver: str, source: str = "bmcl"):
        try:
            need = required_java(mc)
            major, line = java_version()
            self.log(f"Java：{line}")
            if major and major < need:
                raise RuntimeError(
                    f"Minecraft {mc} 需要 Java {need} 或更高，当前是 Java {major}。\n"
                    f"请先安装/指定 Java {need} 再试。")
            jar = CACHE_DIR / f"forge-{mc}-{ver}-installer.jar"
            if jar.exists() and jar.stat().st_size > 1024 * 512:
                self.log(f"已缓存：{jar.name}")
                self.job["percent"] = 40
            else:
                self._download(mc, ver, jar)

            self.job["phase"] = "安装"
            self.job["message"] = "正在运行 Forge 安装器（会下载依赖，可能几分钟）"
            mirror = MAVEN_MIRRORS.get(source, "")
            cmd = [str(JAVA), "-jar", str(jar), "--installServer", str(BASE)]
            if mirror:
                cmd += ["--mirror", mirror]
            self.log("执行：" + " ".join(cmd[1:]))
            if mirror:
                self.log(f"依赖下载走镜像：{mirror}")
            flags = 0x08000000 if os.name == "nt" else 0
            proc = subprocess.Popen(
                cmd, cwd=str(BASE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", creationflags=flags)
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.log(line)
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"安装器退出码 {proc.returncode}，详见上方日志")

            info = detect_forge()
            if not info["kind"]:
                raise RuntimeError("安装器执行完了，但没检测到 Forge，请把日志发给开发者")
            global FORGE, FORGE_ARGS
            FORGE, FORGE_ARGS = info, info["args"]
            self.job["percent"] = 100
            self.job["phase"] = "完成"
            self.job["message"] = f"已安装 Forge {info['mc']}-{info['forge']}"
            self.log(self.job["message"])
        except Exception as e:
            self.job["error"] = str(e)
            self.job["message"] = f"安装失败：{e}"
            self.log(self.job["message"])
        finally:
            self.job["running"] = False


FORGEINST = ForgeInstall()
