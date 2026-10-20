# -*- coding: utf-8 -*-
"""
Minecraft 服务端控制台 —— Qt 桌面界面

界面层只负责显示与交互，所有实际动作都调 core.py。
关闭窗口 = 先让服务器保存存档、再退出面板，绝不断电式退出。
"""
import html
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QIcon, QAction, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QPlainTextEdit, QCheckBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QStackedWidget, QListWidget, QListWidgetItem, QFrame, QProgressBar,
    QMessageBox, QScrollArea, QSizePolicy, QAbstractItemView, QButtonGroup,
)

import core
from quickcmd import QuickCommandPanel
from forge_dialog import ForgeDialog

APP_TITLE = "Minecraft 控制台"


def _icon_dir() -> Path:
    """图标目录：打包后资源被放到 _MEIPASS 根目录；源码运行时用 assets/（没有就用脚本同目录）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    here = Path(__file__).resolve().parent
    cand = here / "assets"
    return cand if cand.is_dir() else here


CHECK_SVG = (_icon_dir() / "check.svg").as_posix()
ARROW_UP = (_icon_dir() / "arrow_up.svg").as_posix()
ARROW_DOWN = (_icon_dir() / "arrow_down.svg").as_posix()
TICK = f"image: url('{CHECK_SVG}');"

C = {
    "bg": "#f4f6f4", "card": "#ffffff", "border": "#e2e7e2", "text": "#1d2521",
    "muted": "#6b7a71", "green": "#2f7d4f", "green_dark": "#25633f",
    "green_soft": "#e9f3ed", "red": "#c0392b", "red_soft": "#fdecea",
    "amber": "#b7791f", "amber_soft": "#fdf5e6",
    "con_bg": "#101613", "con_text": "#cfe3d6",
}

QSS = f"""
* {{ outline: none; }}
QWidget {{ background: {C['bg']}; color: {C['text']};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px; }}
QLabel {{ background: transparent; }}
QWidget#fldBox {{ background: transparent; }}
QFrame#sidebar {{ background: {C['card']}; border-right: 1px solid {C['border']}; }}
QLabel#appTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#appSub {{ font-size: 11px; color: {C['muted']}; }}
QLabel#muted {{ color: {C['muted']}; font-size: 12px; }}
QLabel#statV {{ font-size: 18px; font-weight: 600; }}
QLabel#statK {{ font-size: 11px; color: {C['muted']}; }}
QLabel#h3 {{ font-size: 14px; font-weight: 600; }}

QFrame#card {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 12px; }}

QPushButton {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 8px;
    padding: 7px 14px; color: {C['text']}; }}
QPushButton:hover {{ background: #f7f9f7; border-color: #d3dbd3; }}
QPushButton:pressed {{ background: #eef2ee; }}
QPushButton:disabled {{ color: #a9b3ac; background: #f2f4f2; border-color: {C['border']}; }}
QPushButton[cls="primary"] {{ background: {C['green']}; border-color: {C['green']}; color: white; font-weight: 600; }}
QPushButton[cls="primary"]:hover {{ background: {C['green_dark']}; border-color: {C['green_dark']}; }}
QPushButton[cls="primary"]:disabled {{ background: #a8c6b4; border-color: #a8c6b4; color: #f0f4f1; }}
QPushButton[cls="danger"] {{ color: {C['red']}; border-color: #f0c9c4; }}
QPushButton[cls="danger"]:hover {{ background: {C['red_soft']}; }}
QPushButton[cls="ghost"] {{ background: transparent; border: none; color: {C['muted']}; padding: 5px 8px; }}
QPushButton[cls="ghost"]:hover {{ background: #eef2ee; color: {C['text']}; }}
QPushButton[cls="chip"] {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 12px;
    padding: 4px 11px; font-size: 12px; color: {C['muted']}; }}
QPushButton[cls="chip"]:hover {{ border-color: {C['green']}; color: {C['green']}; background: {C['green_soft']}; }}

QPushButton[cls="seg"] {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 8px;
    padding: 7px 20px; }}
QPushButton[cls="seg"]:hover {{ border-color: {C['green']}; }}
QPushButton[cls="seg"]:checked {{ background: {C['green_soft']}; color: {C['green']};
    border-color: {C['green']}; font-weight: 600; }}

QPushButton[cls="nav"] {{ background: transparent; border: none; border-radius: 8px;
    padding: 9px 12px; text-align: left; color: {C['muted']}; font-size: 13px; }}
QPushButton[cls="nav"]:hover {{ background: #f2f5f2; color: {C['text']}; }}
QPushButton[cls="nav"]:checked {{ background: {C['green_soft']}; color: {C['green']}; font-weight: 600; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {C['card']}; border: 1px solid {C['border']}; border-radius: 8px;
    padding: 6px 9px; selection-background-color: {C['green']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {C['green']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background: #f5f7f5; color: #9aa79f; }}

QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right; width: 18px;
    border: none; background: transparent; margin: 3px 3px 0 0; border-radius: 4px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right; width: 18px;
    border: none; background: transparent; margin: 0 3px 3px 0; border-radius: 4px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: #eef2ee; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url('{ARROW_UP}'); width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url('{ARROW_DOWN}'); width: 9px; height: 9px; }}

QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url('{ARROW_DOWN}'); width: 10px; height: 10px; margin-right: 7px; }}
QComboBox QAbstractItemView {{ border: 1px solid {C['border']}; background: white; selection-background-color: {C['green_soft']};
    selection-color: {C['green']}; }}

QCheckBox::indicator, QListWidget::indicator {{
    width: 15px; height: 15px; border: 1px solid #c9d3cb; border-radius: 4px; background: #fff; }}
QCheckBox::indicator:hover, QListWidget::indicator:hover {{ border-color: {C['green']}; }}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{
    background: {C['green']}; border-color: {C['green']}; {TICK} }}
QCheckBox::indicator:disabled {{ background: #eef2ee; border-color: #dde4de; }}

QPlainTextEdit#console {{ background: {C['con_bg']}; color: {C['con_text']}; border: none;
    border-radius: 8px;
    font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px;
    selection-background-color: #2f4a3c; }}

QTableWidget {{ background: {C['card']}; border: none; gridline-color: transparent; }}
QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid #f0f3f0; }}
QTableWidget::item:selected {{ background: {C['green_soft']}; color: {C['text']}; }}
QHeaderView::section {{ background: #fafcfa; border: none; border-bottom: 1px solid {C['border']};
    padding: 7px 8px; color: {C['muted']}; font-size: 12px; }}

QListWidget {{ background: {C['card']}; border: none; }}
QListWidget::item {{ padding: 8px 6px; border-bottom: 1px solid #f0f3f0; }}
QListWidget::item:selected {{ background: {C['green_soft']}; color: {C['text']}; }}

QCheckBox {{ spacing: 7px; }}
QProgressBar {{ border: none; background: #eef2ee; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {C['green']}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #cfd8d0; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #b7c3b9; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: #cfd8d0; border-radius: 5px; min-width: 28px; }}
QToolTip {{ background: #2b3a31; color: white; border: none; padding: 5px 8px; }}
"""

LOG_COLORS = {
    "error": "#f08d80", "warn": "#e8c37a", "ok": "#7fd6a1",
    "trace": "#6f8579", "info": C["con_text"],
}


def card(*, margins=(16, 14, 16, 14), spacing=10):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return f, lay


def hline():
    ln = QFrame()
    ln.setFrameShape(QFrame.Shape.HLine)
    ln.setStyleSheet(f"color: {C['border']};")
    return ln


class CmdEdit(QLineEdit):
    """带 ↑↓ 历史记录的命令输入框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hist = []
        self.idx = 0

    def push(self, text: str):
        self.hist.append(text)
        self.idx = len(self.hist)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Up and self.idx > 0:
            self.idx -= 1
            self.setText(self.hist[self.idx])
            return
        if k == Qt.Key.Key_Down:
            if self.idx < len(self.hist) - 1:
                self.idx += 1
                self.setText(self.hist[self.idx])
            else:
                self.idx = len(self.hist)
                self.clear()
            return
        super().keyPressEvent(e)


class Panel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1020, 660)
        self.resize(1180, 780)

        self._log_seq = 0
        self._hist = []
        self._hist_i = 0
        self._mods_guard = False
        self._closing = False
        self._auto_yes = False
        self._restart_pending = False
        self._last_state = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 16, 18, 14)
        rl.setSpacing(12)
        rl.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_console())
        self.stack.addWidget(self._page_players())
        self.stack.addWidget(self._page_settings())
        self.stack.addWidget(self._page_backups())
        self.stack.addWidget(self._page_mods())
        self.stack.currentChanged.connect(self._sync_nav)
        rl.addWidget(self.stack, 1)

        rl.addWidget(self._build_statusbar())
        root.addWidget(right, 1)

        # 定时器
        self.t_status = QTimer(self)
        self.t_status.timeout.connect(self.tick_status)
        self.t_status.start(1000)
        self.t_log = QTimer(self)
        self.t_log.timeout.connect(self.tick_log)
        self.t_log.start(400)

        self.tick_status()
        self.tick_log()
        self.refresh_whitelist()
        self.refresh_ban()
        self.refresh_access()
        self.refresh_ops()
        self.load_props()
        self.load_jvm()
        self.refresh_backups()
        self.refresh_worlds()
        self.refresh_mods()
        self.refresh_forge_label()

    # ------------------------------------------------------------ 侧边栏
    def _sync_nav(self, idx):
        b = self.nav_group.button(idx)
        if b and not b.isChecked():
            b.setChecked(True)

    def _build_sidebar(self):
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(196)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(6)

        title = QLabel(APP_TITLE)
        title.setObjectName("appTitle")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("appSub")
        lay.addWidget(title)
        lay.addWidget(self.lbl_sub)
        lay.addSpacing(14)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        items = [("服务器控制台", 0), ("玩家与白名单", 1), ("服务器设置", 2),
                 ("存档管理", 3), ("Mod 管理", 4)]
        for text, idx in items:
            b = QPushButton(text)
            b.setProperty("cls", "nav")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if idx == 0:
                b.setChecked(True)
            b.clicked.connect(lambda _=False, i=idx: self.stack.setCurrentIndex(i))
            self.nav_group.addButton(b, idx)
            lay.addWidget(b)

        lay.addStretch(1)
        self.lbl_base = QLabel("")
        self.lbl_base.setObjectName("muted")
        self.lbl_base.setWordWrap(True)
        lay.addWidget(self.lbl_base)
        lay.addSpacing(6)

        q = QPushButton("退出面板")
        q.setProperty("cls", "ghost")
        q.clicked.connect(self.on_quit)
        lay.addWidget(q)
        return bar

    # ------------------------------------------------------------ 顶部
    def _build_header(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.pill = QLabel("已停止")
        self.pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pill.setMinimumWidth(110)
        self.pill.setFixedHeight(32)
        self._set_pill("stop")

        self.lbl_server = QLabel("")
        self.lbl_server.setObjectName("muted")

        self.btn_start = QPushButton("启动")
        self.btn_start.setToolTip("启动 Minecraft 服务器（约需 1 分钟）")
        self.btn_start.setProperty("cls", "primary")
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setToolTip("让服务器保存存档后正常关闭，不会丢进度")
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_restart = QPushButton("重启")
        self.btn_restart.setToolTip("保存关闭后自动重新启动")
        self.btn_restart.clicked.connect(self.on_restart)
        self.btn_kill = QPushButton("强杀")
        self.btn_kill.setToolTip("直接杀死进程，会丢未保存进度，仅用于卡死时")
        self.btn_kill.setProperty("cls", "danger")
        self.btn_kill.clicked.connect(self.on_kill)
        self.btn_kill.setVisible(False)

        lay.addWidget(self.pill)
        lay.addWidget(self.lbl_server)
        lay.addStretch(1)
        for b in (self.btn_start, self.btn_stop, self.btn_restart, self.btn_kill):
            lay.addWidget(b)
        return w

    def _set_pill(self, kind):
        style = {
            "run": f"color:{C['green']}; background:{C['green_soft']}; border:1px solid #cfe6d8;",
            "mid": f"color:{C['amber']}; background:{C['amber_soft']}; border:1px solid #f2e3c2;",
            "stop": f"color:{C['muted']}; background:#f2f4f2; border:1px solid {C['border']};",
        }[kind]
        self.pill.setStyleSheet(f"QLabel {{ {style} border-radius:16px; font-weight:600; font-size:12px; }}")

    def _build_statusbar(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 0, 2, 0)
        self.lbl_footer = QLabel("")
        self.lbl_footer.setObjectName("muted")
        lay.addWidget(self.lbl_footer)
        lay.addStretch(1)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("muted")
        lay.addWidget(self.lbl_hint)
        return w

    # ------------------------------------------------------------ 控制台
    def _page_console(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        f, fl = card(margins=(14, 12, 14, 12), spacing=10)
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(4000)
        self.console.setPlaceholderText("服务器输出会显示在这里")
        fl.addWidget(self.console, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.cmd = CmdEdit()
        self.cmd.setPlaceholderText("输入服务器指令后回车执行，例如：list / say 你好 / whitelist add 玩家名")
        self.cmd.setFont(QFont("Consolas", 10))
        self.cmd.returnPressed.connect(self.on_command)
        b_send = QPushButton("发送")
        b_send.setProperty("cls", "primary")
        b_send.clicked.connect(self.on_command)
        row.addWidget(self.cmd, 1)
        row.addWidget(b_send)
        fl.addLayout(row)

        chips = QHBoxLayout()
        chips.setSpacing(7)
        for text, c in [("list", "list"), ("save-all", "save-all"),
                        ("天气放晴", "weather clear"), ("设为白天", "time set day"),
                        ("死亡不掉落", "gamerule keepInventory true"),
                        ("白名单", "whitelist list")]:
            b = QPushButton(text)
            b.setProperty("cls", "chip")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, cmd=c: self._fill_cmd(cmd))
            chips.addWidget(b)
        chips.addStretch(1)

        self.cb_auto = QCheckBox("自动滚动")
        self.cb_auto.setChecked(True)
        self.cb_trace = QCheckBox("显示堆栈")
        self.cb_trace.stateChanged.connect(lambda: self.rebuild_log())
        b_clear = QPushButton("清屏")
        b_clear.setProperty("cls", "ghost")
        b_clear.clicked.connect(self.clear_log)
        chips.addWidget(self.cb_auto)
        chips.addWidget(self.cb_trace)
        chips.addWidget(b_clear)
        fl.addLayout(chips)
        lay.addWidget(f, 1)

        # 下半屏：一键指令
        self.quick = QuickCommandPanel(self.on_cmd)
        lay.addWidget(self.quick, 1)
        return w

    def _fill_cmd(self, cmd):
        self.cmd.setText(cmd)
        self.cmd.setFocus()

    def on_command(self):
        text = self.cmd.text().strip()
        if not text:
            return
        ok, msg = core.SRV.command(text)
        if not ok:
            QMessageBox.warning(self, "发送失败", msg)
            return
        self.cmd.push(text)
        self.cmd.clear()

    def clear_log(self):
        self.console.clear()

    def rebuild_log(self):
        self.console.clear()
        for line in list(core.SRV.lines)[-800:]:
            self._append_line(line, scroll=False)
        self._scroll_end()

    def _append_line(self, line, scroll=True):
        if line["level"] == "trace" and not self.cb_trace.isChecked():
            return
        color = LOG_COLORS.get(line["level"], C["con_text"])
        bold = " font-weight:600;" if line["level"] == "ok" else ""
        self.console.appendHtml(
            f'<span style="color:{color};{bold}">{html.escape(line["text"])}</span>'
        )
        if scroll and self.cb_auto.isChecked():
            self._scroll_end()

    def _scroll_end(self):
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------ 玩家
    def _page_players(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # 访问控制（白名单 ⇄ 黑名单）
        f0, l0 = card()
        head0 = QHBoxLayout()
        t0 = QLabel("进服限制")
        t0.setObjectName("h3")
        head0.addWidget(t0)
        head0.addStretch(1)
        self.btn_ban_mode = QPushButton("黑名单模式")
        self.btn_ban_mode.setProperty("cls", "seg")
        self.btn_ban_mode.setCheckable(True)
        self.btn_ban_mode.clicked.connect(lambda: self.on_mode("blacklist"))
        self.btn_wl_mode = QPushButton("白名单模式")
        self.btn_wl_mode.setProperty("cls", "seg")
        self.btn_wl_mode.setCheckable(True)
        self.btn_wl_mode.clicked.connect(lambda: self.on_mode("whitelist"))
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        grp.addButton(self.btn_wl_mode)
        grp.addButton(self.btn_ban_mode)
        head0.addWidget(self.btn_ban_mode)
        head0.addWidget(self.btn_wl_mode)
        l0.addLayout(head0)
        self.lbl_access = QLabel("")
        self.lbl_access.setObjectName("muted")
        self.lbl_access.setWordWrap(True)
        l0.addWidget(self.lbl_access)
        lay.addWidget(f0)

        # 在线
        f1, l1 = card()
        head = QHBoxLayout()
        t = QLabel("在线玩家")
        t.setObjectName("h3")
        self.lbl_online_n = QLabel("")
        self.lbl_online_n.setObjectName("muted")
        head.addWidget(t)
        head.addWidget(self.lbl_online_n)
        head.addStretch(1)
        l1.addLayout(head)
        self.tbl_online = self._table(["玩家", "操作"], last_width=200)
        self.tbl_online.setMaximumHeight(130)
        l1.addWidget(self.tbl_online)
        lay.addWidget(f1)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        # 白名单
        f2, l2 = card()
        t2 = QLabel("白名单（只放行名单内）")
        t2.setObjectName("h3")
        l2.addWidget(t2)
        hint = QLabel("只有白名单模式开启时才生效。离线账号的 UUID 会自动算，不用手填。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        l2.addWidget(hint)
        r = QHBoxLayout()
        self.wl_name = QLineEdit()
        self.wl_name.setPlaceholderText("玩家名（字母/数字/下划线）")
        self.wl_name.returnPressed.connect(self.on_wl_add)
        b = QPushButton("加入")
        b.clicked.connect(self.on_wl_add)
        r.addWidget(self.wl_name, 1)
        r.addWidget(b)
        l2.addLayout(r)
        self.tbl_wl = self._table(["玩家", "操作"], last_width=92)
        l2.addWidget(self.tbl_wl, 1)
        bottom.addWidget(f2, 1)

        # 黑名单
        fban, lban = card()
        tban = QLabel("黑名单（封禁）")
        tban.setObjectName("h3")
        lban.addWidget(tban)
        hban = QLabel("被封禁的人进不了服，其余人都能进。在线时封禁会立刻踢出。")
        hban.setObjectName("muted")
        hban.setWordWrap(True)
        lban.addWidget(hban)
        rban = QHBoxLayout()
        self.ban_name = QLineEdit()
        self.ban_name.setPlaceholderText("玩家名")
        self.ban_name.returnPressed.connect(self.on_ban_add)
        b_ban = QPushButton("封禁")
        b_ban.clicked.connect(self.on_ban_add)
        rban.addWidget(self.ban_name, 1)
        rban.addWidget(b_ban)
        lban.addLayout(rban)
        self.tbl_ban = self._table(["玩家", "操作"], last_width=92)
        lban.addWidget(self.tbl_ban, 1)
        bottom.addWidget(fban, 1)

        # OP
        f3, l3 = card()
        t3 = QLabel("管理员（OP）")
        t3.setObjectName("h3")
        l3.addWidget(t3)
        hint2 = QLabel("OP 拥有全部指令权限，只给自己和信任的人。")
        hint2.setObjectName("muted")
        hint2.setWordWrap(True)
        l3.addWidget(hint2)
        r2 = QHBoxLayout()
        self.op_name = QLineEdit()
        self.op_name.setPlaceholderText("玩家名")
        self.op_name.returnPressed.connect(self.on_op_add)
        b2 = QPushButton("设为 OP")
        b2.clicked.connect(self.on_op_add)
        r2.addWidget(self.op_name, 1)
        r2.addWidget(b2)
        l3.addLayout(r2)
        self.tbl_ops = self._table(["玩家", "操作"], last_width=92)
        l3.addWidget(self.tbl_ops, 1)
        bottom.addWidget(f3, 1)

        lay.addLayout(bottom, 1)
        return w

    def _table(self, headers, last_width=None):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        hh = t.horizontalHeader()
        if last_width:
            hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Fixed)
            hh.resizeSection(len(headers) - 1, last_width)
        else:
            hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setDefaultSectionSize(38)
        return t

    def refresh_online(self, names):
        self.lbl_online_n.setText(f"（{len(names)} 人在线）" if names else "")
        self.tbl_online.setRowCount(0)
        if self._last_state in (None, "stopped"):
            self.tbl_online.setRowCount(1)
            it = QTableWidgetItem("服务器未运行")
            it.setForeground(Qt.GlobalColor.gray)
            self.tbl_online.setItem(0, 0, it)
            return
        if not names:
            self.tbl_online.setRowCount(1)
            it = QTableWidgetItem("还没有人进服")
            it.setForeground(Qt.GlobalColor.gray)
            self.tbl_online.setItem(0, 0, it)
            return
        for i, n in enumerate(names):
            self.tbl_online.insertRow(i)
            self.tbl_online.setItem(i, 0, QTableWidgetItem(n))
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 2, 0, 2)
            h.setSpacing(6)
            b1 = QPushButton("踢出")
            b1.setProperty("cls", "ghost")
            b1.clicked.connect(lambda _=False, name=n: self.on_cmd(f"kick {name}"))
            b2 = QPushButton("设为 OP")
            b2.setProperty("cls", "ghost")
            b2.clicked.connect(lambda _=False, name=n: self.on_op(name, True))
            h.addWidget(b1)
            h.addWidget(b2)
            h.addStretch(1)
            self.tbl_online.setCellWidget(i, 1, box)

    def refresh_whitelist(self):
        data = core.get_players().get("whitelist", [])
        self.tbl_wl.setRowCount(0)
        if not data:
            self.tbl_wl.setRowCount(1)
            it = QTableWidgetItem("白名单是空的")
            it.setForeground(Qt.GlobalColor.gray)
            self.tbl_wl.setItem(0, 0, it)
            return
        for i, w in enumerate(data):
            self.tbl_wl.insertRow(i)
            self.tbl_wl.setItem(i, 0, QTableWidgetItem(w["name"]))
            b = QPushButton("移出")
            b.setProperty("cls", "ghost")
            b.clicked.connect(lambda _=False, n=w["name"]: self.on_wl_remove(n))
            self.tbl_wl.setCellWidget(i, 1, b)

    def refresh_ops(self):
        data = core.get_players().get("ops", [])
        self.tbl_ops.setRowCount(0)
        if not data:
            self.tbl_ops.setRowCount(1)
            it = QTableWidgetItem("还没有设置 OP")
            it.setForeground(Qt.GlobalColor.gray)
            self.tbl_ops.setItem(0, 0, it)
            return
        for i, o in enumerate(data):
            self.tbl_ops.insertRow(i)
            self.tbl_ops.setItem(i, 0, QTableWidgetItem(o["name"]))
            b = QPushButton("取消")
            b.setProperty("cls", "ghost")
            b.clicked.connect(lambda _=False, n=o["name"]: self.on_op(n, False))
            self.tbl_ops.setCellWidget(i, 1, b)

    def on_wl_add(self):
        name = self.wl_name.text().strip()
        if not name:
            return
        ok, msg = core.whitelist_add(name)
        if ok:
            self.wl_name.clear()
            self.refresh_whitelist()
        else:
            QMessageBox.warning(self, "加入失败", msg)

    # ---- 进服限制 / 黑名单
    def refresh_access(self):
        mode = core.get_players().get("mode", "blacklist")
        self.btn_wl_mode.setChecked(mode == "whitelist")
        self.btn_ban_mode.setChecked(mode == "blacklist")
        if mode == "whitelist":
            self.lbl_access.setText("白名单模式：只有白名单里的玩家能进服，其他人一律拒绝（最严）。")
            self.lbl_access.setStyleSheet("color: #2f7d4f; font-size: 12px;")
        else:
            self.lbl_access.setText("黑名单模式：被封禁的玩家进不来，其余人都能进。想更严就切到白名单模式。")
            self.lbl_access.setStyleSheet("color: #6b7a71; font-size: 12px;")

    def on_mode(self, mode):
        core.set_access_mode(mode)
        self.refresh_access()
        self.load_props()          # 同步设置页的「开启白名单」复选框
        self.refresh_whitelist()

    def refresh_ban(self):
        data = core.get_players().get("banned", [])
        self.tbl_ban.setRowCount(0)
        if not data:
            self.tbl_ban.setRowCount(1)
            it = QTableWidgetItem("黑名单是空的")
            it.setForeground(Qt.GlobalColor.gray)
            self.tbl_ban.setItem(0, 0, it)
            return
        for i, b in enumerate(data):
            self.tbl_ban.insertRow(i)
            self.tbl_ban.setItem(i, 0, QTableWidgetItem(b["name"]))
            btn = QPushButton("解除")
            btn.setProperty("cls", "ghost")
            btn.clicked.connect(lambda _=False, n=b["name"]: self.on_ban_remove(n))
            self.tbl_ban.setCellWidget(i, 1, btn)

    def on_ban_add(self):
        name = self.ban_name.text().strip()
        if not name:
            return
        ok, msg = core.ban_add(name)
        if ok:
            self.ban_name.clear()
            self.refresh_ban()
        else:
            QMessageBox.warning(self, "封禁失败", msg)

    def on_ban_remove(self, name):
        if QMessageBox.question(self, "解除封禁", f"解除对 {name} 的封禁？") != QMessageBox.StandardButton.Yes:
            return
        ok, msg = core.ban_remove(name)
        if ok:
            self.refresh_ban()
        else:
            QMessageBox.warning(self, "操作失败", msg)

    def on_wl_remove(self, name):
        if QMessageBox.question(self, "移出白名单", f"把 {name} 移出白名单？") != QMessageBox.StandardButton.Yes:
            return
        ok, msg = core.whitelist_remove(name)
        if ok:
            self.refresh_whitelist()
        else:
            QMessageBox.warning(self, "操作失败", msg)

    def on_op_add(self):
        name = self.op_name.text().strip()
        if not name:
            return
        self.on_op(name, True)
        self.op_name.clear()

    def on_op(self, name, enable):
        ok, msg = core.set_op(name, enable)
        if ok:
            self.refresh_ops()
        else:
            QMessageBox.warning(self, "操作失败", msg)

    def on_cmd(self, cmd):
        ok, msg = core.SRV.command(cmd)
        if not ok:
            QMessageBox.warning(self, "发送失败", msg)

    # ------------------------------------------------------------ 设置
    def _page_settings(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)

        f, fl = card()
        t = QLabel("Forge 版本")
        t.setObjectName("h3")
        fl.addWidget(t)
        self.lb_forge = QLabel("")
        self.lb_forge.setObjectName("muted")
        self.lb_forge.setWordWrap(True)
        fl.addWidget(self.lb_forge)
        r0 = QHBoxLayout()
        b0 = QPushButton("选择并安装 Forge…")
        b0.setProperty("cls", "primary")
        b0.clicked.connect(self.open_forge_dialog)
        r0.addWidget(b0)
        hint0 = QLabel("换 Forge 版本、或这个目录还没装 Forge 时用这里")
        hint0.setObjectName("muted")
        r0.addWidget(hint0)
        r0.addStretch(1)
        fl.addLayout(r0)
        lay.addWidget(f)

        f1, fl1 = card()
        t1 = QLabel("server.properties")
        t1.setObjectName("h3")
        fl1.addWidget(t1)
        hint = QLabel("改完点保存。端口与正版验证需要重启服务器才生效，其余大多数即时生效。")
        hint.setObjectName("muted")
        fl1.addWidget(hint)
        self.props_grid = QGridLayout()
        self.props_grid.setHorizontalSpacing(18)
        self.props_grid.setVerticalSpacing(10)
        fl1.addLayout(self.props_grid)
        row = QHBoxLayout()
        b = QPushButton("保存设置")
        b.setProperty("cls", "primary")
        b.clicked.connect(self.on_save_props)
        row.addWidget(b)
        row.addStretch(1)
        b2 = QPushButton("打开服务器目录")
        b2.setProperty("cls", "ghost")
        b2.clicked.connect(lambda: core.open_folder("base"))
        row.addWidget(b2)
        fl1.addLayout(row)
        lay.addWidget(f1)

        f2, fl2 = card()
        t2 = QLabel("内存分配（JVM）")
        t2.setObjectName("h3")
        fl2.addWidget(t2)
        h2 = QLabel("40+ mod 的 Forge 服建议最大内存 6-8GB，不要超过物理内存的一半。改完需重启。")
        h2.setObjectName("muted")
        fl2.addWidget(h2)
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(10)
        g.addWidget(QLabel("初始内存 -Xms (MB)"), 0, 0)
        self.sp_xms = QSpinBox()
        self.sp_xms.setRange(512, 65536)
        self.sp_xms.setSingleStep(512)
        g.addWidget(self.sp_xms, 1, 0)
        g.addWidget(QLabel("最大内存 -Xmx (MB)"), 0, 1)
        self.sp_xmx = QSpinBox()
        self.sp_xmx.setRange(512, 65536)
        self.sp_xmx.setSingleStep(512)
        g.addWidget(self.sp_xmx, 1, 1)
        g.setColumnStretch(2, 1)
        fl2.addLayout(g)
        r2 = QHBoxLayout()
        b3 = QPushButton("保存内存设置")
        b3.clicked.connect(self.on_save_jvm)
        r2.addWidget(b3)
        r2.addStretch(1)
        fl2.addLayout(r2)
        lay.addWidget(f2)
        lay.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self._prop_widgets = {}
        return w

    def load_props(self):
        vals = core.read_props()
        running = core.SRV.status()["running"]
        while self.props_grid.count():
            it = self.props_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._prop_widgets.clear()

        for i, (key, label, typ) in enumerate(core.PROP_SCHEMA):
            r, c = divmod(i, 2)
            box = QWidget()
            box.setObjectName("fldBox")
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(4)
            lab = QLabel(label)
            lab.setObjectName("muted")
            v.addWidget(lab)

            val = vals.get(key, "")
            if typ == "bool":
                wd = QCheckBox("开启")
                wd.setChecked(val == "true")
            elif typ.startswith("select:"):
                wd = QComboBox()
                wd.addItems(typ.split(":", 1)[1].split(","))
                if val in [wd.itemText(i2) for i2 in range(wd.count())]:
                    wd.setCurrentText(val)
            elif typ == "number":
                wd = QSpinBox()
                wd.setRange(0, 999999)
                try:
                    wd.setValue(int(val))
                except ValueError:
                    wd.setValue(0)
            else:
                wd = QLineEdit(val)
            if key == "server-port" and running:
                wd.setEnabled(False)
            self._prop_widgets[key] = wd
            v.addWidget(wd)
            self.props_grid.addWidget(box, r, c)

    def on_save_props(self):
        values = {}
        for key, _, typ in core.PROP_SCHEMA:
            wd = self._prop_widgets.get(key)
            if wd is None:
                continue
            if isinstance(wd, QCheckBox):
                values[key] = "true" if wd.isChecked() else "false"
            elif isinstance(wd, QComboBox):
                values[key] = wd.currentText()
            elif isinstance(wd, QSpinBox):
                values[key] = str(wd.value())
            elif isinstance(wd, QLineEdit):
                if wd.isEnabled():
                    values[key] = wd.text()
        try:
            core.write_props(values)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        need = any(k in ("server-port", "online-mode") for k in values)
        QMessageBox.information(self, "已保存",
                                "设置已保存。" + ("\n端口/正版验证的改动需重启服务器生效。" if need else ""))
        self.load_props()

    def load_jvm(self):
        d = core.read_jvm()
        if d.get("xms_mb"):
            self.sp_xms.setValue(d["xms_mb"])
        if d.get("xmx_mb"):
            self.sp_xmx.setValue(d["xmx_mb"])

    def on_save_jvm(self):
        ok, msg = core.write_jvm(self.sp_xms.value(), self.sp_xmx.value())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "内存设置", msg)

    # ------------------------------------------------------------ Forge
    def refresh_forge_label(self):
        info = core.detect_forge()
        if info["kind"]:
            major, _ = core.java_version()
            how = "win_args" if info["kind"] == "win_args" else info["jar"]
            self.lb_forge.setText(
                f"当前：Forge {info['mc']}-{info['forge']}　启动方式：{how}　|　Java {major}")
            self.lbl_sub.setText(f"Forge {info['mc']}-{info['forge']}")
        else:
            self.lb_forge.setText("当前：还没检测到 Forge —— 点右边按钮选版本安装后就能启动。")
            self.lbl_sub.setText("未安装 Forge")

    def open_forge_dialog(self, first_run=False):
        d = ForgeDialog(self, first_run=first_run)
        d.exec()
        self.refresh_forge_label()
        self.load_props()
        self.tick_status()

    # ------------------------------------------------------------ 备份
    def _page_backups(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # 切换 / 新建存档
        fw, flw = card()
        hw = QHBoxLayout()
        tw = QLabel("当前存档")
        tw.setObjectName("h3")
        self.lbl_cur_world = QLabel("")
        self.lbl_cur_world.setObjectName("muted")
        hw.addWidget(tw)
        hw.addWidget(self.lbl_cur_world)
        hw.addStretch(1)
        flw.addLayout(hw)

        self.tbl_worlds = self._table(["存档", "大小", "修改时间", "操作"], last_width=120)
        self.tbl_worlds.setMaximumHeight(150)
        flw.addWidget(self.tbl_worlds)

        rn = QHBoxLayout()
        rn.setSpacing(8)
        self.new_world = QLineEdit()
        self.new_world.setPlaceholderText("新存档名，例如 world2 / 空岛生存")
        self.new_world.returnPressed.connect(self.on_switch_world)
        rn.addWidget(self.new_world, 1)
        self.cb_wtype = QComboBox()
        self.cb_wtype.addItem("默认地形", "")
        self.cb_wtype.addItem("超平坦", "minecraft:flat")
        self.cb_wtype.addItem("巨型生物群系", "minecraft:large_biomes")
        self.cb_wtype.addItem("放大化", "minecraft:amplified")
        self.cb_wtype.addItem("单一生物群系", "minecraft:single_biome_surface")
        rn.addWidget(self.cb_wtype)
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("种子（可留空）")
        self.seed_edit.setMaximumWidth(140)
        rn.addWidget(self.seed_edit)
        b_new = QPushButton("新建/切换到此存档")
        b_new.setProperty("cls", "primary")
        b_new.clicked.connect(self.on_switch_world)
        rn.addWidget(b_new)
        flw.addLayout(rn)

        tip = QLabel("切换存档 = 改 level-name，必须重启服务器才生效；新存档首次启动会自动生成世界。")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        flw.addWidget(tip)
        lay.addWidget(fw)

        f, fl = card()
        head = QHBoxLayout()
        t = QLabel("存档备份")
        t.setObjectName("h3")
        head.addWidget(t)
        head.addStretch(1)
        self.lbl_world = QLabel("")
        self.lbl_world.setObjectName("muted")
        head.addWidget(self.lbl_world)
        fl.addLayout(head)
        hint = QLabel("服务器运行中也能备份：会先暂停自动保存、刷新存档，再打包，完成后恢复自动保存，不会损坏世界。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        fl.addWidget(hint)
        r = QHBoxLayout()
        self.btn_backup = QPushButton("立即备份")
        self.btn_backup.setProperty("cls", "primary")
        self.btn_backup.clicked.connect(self.on_backup)
        r.addWidget(self.btn_backup)
        r.addStretch(1)
        b2 = QPushButton("打开备份目录")
        b2.setProperty("cls", "ghost")
        b2.clicked.connect(lambda: core.open_folder("backups"))
        r.addWidget(b2)
        fl.addLayout(r)

        self.bk_msg = QLabel("")
        self.bk_msg.setObjectName("muted")
        self.bk_msg.setVisible(False)
        fl.addWidget(self.bk_msg)
        self.bk_bar = QProgressBar()
        self.bk_bar.setRange(0, 100)
        self.bk_bar.setVisible(False)
        fl.addWidget(self.bk_bar)
        lay.addWidget(f)

        f2, fl2 = card()
        t2 = QLabel("自动备份")
        t2.setObjectName("h3")
        fl2.addWidget(t2)
        r2 = QHBoxLayout()
        self.cb_auto_bk = QCheckBox("开启")
        self.cb_auto_bk.stateChanged.connect(self.on_auto_toggle)
        r2.addWidget(self.cb_auto_bk)
        r2.addSpacing(10)
        r2.addWidget(QLabel("每"))
        self.sp_hours = QDoubleSpinBox()
        self.sp_hours.setRange(0.5, 48)
        self.sp_hours.setSingleStep(0.5)
        self.sp_hours.setValue(6)
        r2.addWidget(self.sp_hours)
        r2.addWidget(QLabel("小时备份一次（面板开着且服务器运行时才触发）"))
        r2.addStretch(1)
        fl2.addLayout(r2)
        lay.addWidget(f2)

        f3, fl3 = card()
        t3 = QLabel("历史备份")
        t3.setObjectName("h3")
        fl3.addWidget(t3)
        self.tbl_bk = self._table(["文件名", "时间", "大小", "操作"], last_width=92)
        fl3.addWidget(self.tbl_bk, 1)
        lay.addWidget(f3, 1)
        return w

    # ---- 存档切换
    def refresh_worlds(self):
        cur = core.current_world()
        self.lbl_cur_world.setText(f"当前：{cur}")
        worlds = core.list_worlds()
        self.tbl_worlds.setRowCount(0)
        if not worlds:
            self.tbl_worlds.setRowCount(1)
            it = QTableWidgetItem("没检测到存档（新存档启动后会自动出现）")
            it.setForeground(Qt.GlobalColor.gray)
            self.tbl_worlds.setItem(0, 0, it)
            return
        for i, w in enumerate(worlds):
            self.tbl_worlds.insertRow(i)
            self.tbl_worlds.setItem(i, 0, QTableWidgetItem(
                w["name"] + ("（当前）" if w["active"] else "")))
            self.tbl_worlds.setItem(i, 1, QTableWidgetItem(core.human_size(w["size"])))
            self.tbl_worlds.setItem(i, 2, QTableWidgetItem(
                time.strftime("%Y-%m-%d %H:%M", time.localtime(w["mtime"]))))
            btn = QPushButton("切换" if not w["active"] else "已是当前")
            btn.setProperty("cls", "ghost")
            btn.setEnabled(not w["active"])
            btn.clicked.connect(lambda _=False, n=w["name"]: self.on_switch_world(n))
            self.tbl_worlds.setCellWidget(i, 3, btn)

    def on_switch_world(self, name=None):
        name = (name or self.new_world.text()).strip()
        if not name:
            QMessageBox.information(self, "切换存档", "先填一个存档名，或在上面的列表里点「切换」。")
            return
        if core.SRV.status()["running"]:
            QMessageBox.warning(
                self, "请先停止服务器",
                "存档（level-name）只在服务器启动时读取，运行中改不会生效。\n\n"
                "请先点顶部「停止」，再来切换。")
            return
        ok, msg = core.switch_world(name, self.seed_edit.text(), self.cb_wtype.currentData())
        if not ok:
            QMessageBox.warning(self, "无法切换", msg)
            return
        self.new_world.clear()
        self.seed_edit.clear()
        self.refresh_worlds()
        self.load_props()
        QMessageBox.information(self, "已切换", msg + "\n\n现在点「启动」就进入这个存档了。")

    def refresh_backups(self):
        data = core.BK.list()
        self.lbl_world.setText("当前存档 " + core.human_size(core.dir_size(core.WORLD_DIR)))
        job = core.BK.job
        if job["running"]:
            self.bk_msg.setVisible(True)
            self.bk_bar.setVisible(True)
            self.bk_msg.setText(job.get("message") or "备份中…")
            pct = int(job["progress"] / job["total"] * 100) if job.get("total") else 0
            self.bk_bar.setValue(pct)
            self.btn_backup.setEnabled(False)
        else:
            self.btn_backup.setEnabled(True)
            if job.get("message"):
                self.bk_msg.setVisible(True)
                self.bk_msg.setText(job["message"])
                self.bk_bar.setVisible(False)
            else:
                self.bk_msg.setVisible(False)
                self.bk_bar.setVisible(False)

        self.tbl_bk.setRowCount(0)
        if not data:
            self.tbl_bk.setRowCount(1)
            it = QTableWidgetItem("还没有备份")
            it.setForeground(Qt.GlobalColor.gray)
            self.tbl_bk.setItem(0, 0, it)
            return
        for i, b in enumerate(data):
            self.tbl_bk.insertRow(i)
            self.tbl_bk.setItem(i, 0, QTableWidgetItem(b["name"]))
            self.tbl_bk.setItem(i, 1, QTableWidgetItem(b["time"]))
            self.tbl_bk.setItem(i, 2, QTableWidgetItem(b["size_text"]))
            btn = QPushButton("删除")
            btn.setProperty("cls", "ghost")
            btn.clicked.connect(lambda _=False, n=b["name"]: self.on_bk_delete(n))
            self.tbl_bk.setCellWidget(i, 3, btn)

    def on_backup(self):
        ok, msg = core.BK.start("manual")
        if not ok:
            QMessageBox.warning(self, "备份", msg)
        self.refresh_backups()

    def on_bk_delete(self, name):
        if QMessageBox.question(self, "删除备份",
                                f"删除 {name}？此操作不可恢复。") != QMessageBox.StandardButton.Yes:
            return
        core.BK.delete(name)
        self.refresh_backups()

    def on_auto_toggle(self):
        core.AUTO.enabled = self.cb_auto_bk.isChecked()
        try:
            core.AUTO.interval_h = float(self.sp_hours.value())
        except Exception:
            pass
        if core.AUTO.enabled:
            import time as _t
            core.AUTO.last = _t.time()

    # ------------------------------------------------------------ Mod
    def _page_mods(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        f, fl = card()
        head = QHBoxLayout()
        t = QLabel("Mod 管理")
        t.setObjectName("h3")
        head.addWidget(t)
        self.lbl_mods = QLabel("")
        self.lbl_mods.setObjectName("muted")
        head.addWidget(self.lbl_mods)
        head.addStretch(1)
        b = QPushButton("打开 mods 目录")
        b.setProperty("cls", "ghost")
        b.clicked.connect(lambda: core.open_folder("mods"))
        head.addWidget(b)
        fl.addLayout(head)
        hint = QLabel("关掉的 mod 会被移动到 mods-disabled 文件夹，不会删除，随时可以再打开。改动需重启服务器生效。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        fl.addWidget(hint)
        self.mod_search = QLineEdit()
        self.mod_search.setPlaceholderText("搜索 mod 名称")
        self.mod_search.textChanged.connect(self.render_mods)
        fl.addWidget(self.mod_search)
        self.mod_list = QListWidget()
        self.mod_list.itemChanged.connect(self.on_mod_toggle)
        fl.addWidget(self.mod_list, 1)
        lay.addWidget(f, 1)
        self._all_mods = []
        return w

    def refresh_mods(self):
        self._all_mods = core.list_mods()
        self.lbl_mods.setText(f"已启用 {sum(1 for m in self._all_mods if m['enabled'])} / 共 {len(self._all_mods)}")
        self.render_mods()

    def render_mods(self):
        q = self.mod_search.text().lower()
        self._mods_guard = True
        self.mod_list.clear()
        for m in self._all_mods:
            name = m["name"][:-4] if m["name"].lower().endswith(".jar") else m["name"]
            if q and q not in name.lower():
                continue
            item = QListWidgetItem(f"{name}    ·  {m['size_text']}  ·  {m['mtime']}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if m["enabled"] else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, m["name"])
            if not m["enabled"]:
                item.setForeground(Qt.GlobalColor.gray)
            self.mod_list.addItem(item)
        self._mods_guard = False

    def on_mod_toggle(self, item):
        if self._mods_guard:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        enable = item.checkState() == Qt.CheckState.Checked
        ok, msg = core.toggle_mod(name, enable)
        if not ok:
            QMessageBox.warning(self, "操作失败", msg)
        self.refresh_mods()

    # ------------------------------------------------------------ 状态轮询
    def tick_status(self):
        st = core.SRV.status()
        prev = self._last_state
        self._last_state = st["state"]

        text = {"stopped": "已停止", "starting": "启动中", "running": "运行中", "stopping": "关闭中"}[st["state"]]
        self.pill.setText(text + (f"  PID {st['pid']}" if st["pid"] else ""))
        self._set_pill("run" if st["state"] == "running" else
                       ("mid" if st["running"] else "stop"))

        running = st["running"]
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running and st["state"] != "stopping")
        self.btn_restart.setEnabled(running)
        self.btn_kill.setVisible(running)

        avg = st["uptime"]
        self.lbl_server.setText(f"已运行 {self._fmt(avg)}" if running else "服务器未运行")
        self.lbl_footer.setText(
            f"服务端目录：{core.BASE}    |    存档 {core.human_size(core.dir_size(core.WORLD_DIR))}"
        )
        if st["last_error"] and st["state"] == "stopped":
            self.lbl_hint.setText("启动失败：" + st["last_error"][:80])
        else:
            self.lbl_hint.setText("")

        if prev != st["state"]:
            core.SRV.log_file(f"界面状态: {prev} -> {st['state']} (pid={st['pid']})")
            self.refresh_online(st["online"])
            self.refresh_forge_label()
            if st["state"] == "running":
                self.refresh_whitelist()
                self.refresh_ban()
                self.load_props()
        else:
            self.refresh_online(st["online"])

        self.quick.refresh_players(st.get("online") or [])

        if self.stack.currentIndex() == 3:
            self.refresh_backups()
            self.refresh_worlds()

        if self._closing:
            if not running:
                core.SRV.log_file("服务器已停止，退出程序")
                self.close()
            else:
                self._close_wait = getattr(self, "_close_wait", 0) + 1
                if self._close_wait > 150:          # 兜底：2.5 分钟还没停就别等了
                    core.SRV.log_file("等待停服超时，直接退出窗口")
                    self.close()

    @staticmethod
    def _fmt(sec):
        if not sec:
            return "-"
        h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
        if h:
            return f"{h} 小时 {m} 分"
        if m:
            return f"{m} 分 {s} 秒"
        return f"{s} 秒"

    def tick_log(self):
        lines = list(core.SRV.lines)
        if not lines:
            return
        newest = lines[-1]["seq"]
        if newest <= self._log_seq:
            return
        fresh = [l for l in lines if l["seq"] > self._log_seq]
        self._log_seq = newest
        for l in fresh:
            self._append_line(l)

    # ------------------------------------------------------------ 操作
    def on_start(self):
        ok, msg = core.SRV.start()
        if not ok:
            QMessageBox.warning(self, "启动失败", msg)
        self.tick_status()

    def on_stop(self):
        r = QMessageBox.question(
            self, "关闭服务器",
            "确定要关闭服务器吗？\n\n面板会先让服务器保存存档再退出，可能需要几十秒，期间请不要关掉面板。")
        if r != QMessageBox.StandardButton.Yes:
            return
        ok, msg = core.SRV.stop()
        if not ok:
            QMessageBox.warning(self, "操作失败", msg)
        self.tick_status()

    def on_restart(self):
        r = QMessageBox.question(self, "重启服务器", "确定重启？会先保存关闭再自动拉起，约 1-3 分钟。")
        if r != QMessageBox.StandardButton.Yes:
            return
        core.SRV.stop()
        self._restart_pending = True
        QTimer.singleShot(1000, self._wait_restart)

    def _wait_restart(self):
        if core.SRV.status()["running"]:
            QTimer.singleShot(1000, self._wait_restart)
            return
        QTimer.singleShot(1500, core.SRV.start)
        self._restart_pending = False

    def on_kill(self):
        r = QMessageBox.warning(
            self, "强制结束",
            "强制结束会直接杀死 Java 进程，当前未保存的进度会丢失！\n\n"
            "只有在「保存并关闭」卡住时才用。确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        core.SRV.stop(force=True)

    def on_quit(self):
        core.SRV.log_file("用户点了「退出面板」")
        self.close()

    def closeEvent(self, e):
        if self._closing:
            e.accept()
            return
        running = core.SRV.status()["running"]
        core.SRV.log_file(f"关闭窗口请求 (服务器在运行={running})")
        if running:
            if not self._auto_yes:
                r = QMessageBox.question(
                    self, "退出程序",
                    "服务器还在运行。\n\n退出会先让服务器保存存档并关闭，可能需要几十秒。\n确定退出吗？")
                if r != QMessageBox.StandardButton.Yes:
                    e.ignore()
                    return
            self._closing = True
            self.setEnabled(False)
            self.lbl_hint.setText("正在保存存档并关闭服务器，请稍候…")
            core.SRV.stop()
            e.ignore()
            return
        e.accept()

    def showEvent(self, e):
        super().showEvent(e)


def main():
    argv = sys.argv
    if core.handle_uninstall_args(argv):
        return 0

    app = QApplication(argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")            # 统一用 Fusion，QSS 才不会时灵时不灵
    app.setStyleSheet(QSS)

    ico = _icon_dir() / "icon.ico"
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    if not core.PROPS.exists():
        QMessageBox.critical(None, "路径错误",
                             f"找不到 server.properties。\n\n已查找：{core.BASE}\n\n"
                             "请把面板程序放在 Minecraft 服务端目录里（或它下面的 panel 文件夹）。")
        return 2

    if not core.claim_single_instance():
        QMessageBox.information(None, APP_TITLE, "控制面板已经在运行了。\n\n"
                               "请到任务栏找一下已经打开的窗口。")
        return 0

    w = Panel()
    if "--yes" in argv:                 # 自检用：关闭时不弹确认框
        w._auto_yes = True
    w.show()
    core.SRV.log_file(f"界面启动 base={core.BASE} frozen={core.FROZEN}")

    if "--choose-forge" in argv:              # 安装器首次启动 / 没有 Forge 时引导
        QTimer.singleShot(450, lambda: w.open_forge_dialog(first_run=True))

    if "--page" in argv:
        i = argv.index("--page")
        try:
            w.stack.setCurrentIndex(int(argv[i + 1]))
        except (IndexError, ValueError):
            pass

    if "--tab" in argv:                       # 自检用：指定一键指令页签
        i = argv.index("--tab")
        try:
            w.quick.tabs.setCurrentIndex(int(argv[i + 1]))
        except (IndexError, ValueError):
            pass

    if "--dev-start" in argv:                 # 自检用：启动后自动起服
        QTimer.singleShot(800, w.on_start)

    if "--shot" in argv:
        i = argv.index("--shot")
        out = argv[i + 1] if len(argv) > i + 1 else "shot.png"
        delay = 900
        if "--shot-delay" in argv:
            j = argv.index("--shot-delay")
            try:
                delay = int(float(argv[j + 1]) * 1000)
            except (IndexError, ValueError):
                pass

        def _shot():
            import json
            w.grab().save(out)
            try:
                st = core.SRV.status()
                st["log_lines"] = len(core.SRV.lines)
                Path(out).with_suffix(".json").write_text(
                    json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            core.SRV.log_file("自检：截图完成，走正常关闭流程")
            w.close()          # 走真实关闭路径：停服 → 退出

        QTimer.singleShot(delay, _shot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
