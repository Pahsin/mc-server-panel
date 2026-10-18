# -*- coding: utf-8 -*-
"""
Forge 版本选择 / 下载 / 安装对话框。

三个入口共用这一个对话框：
  1. 设置页「Forge 版本 → 选择并安装」
  2. 安装器装完自动首启（MCPanel.exe --choose-forge）
  3. 服务端没检测到 Forge 时，点「启动」引导过来

网络请求全部放在子线程，主线程只更新界面。
"""
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QPlainTextEdit, QFrame, QMessageBox,
)

import core


class _Task(QThread):
    """把阻塞调用丢到子线程：done(结果, 错误文本)。"""
    done = Signal(object, str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(), "")
        except Exception as e:
            self.done.emit(None, str(e))


class ForgeDialog(QDialog):
    def __init__(self, parent=None, first_run=False):
        super().__init__(parent)
        self.first_run = first_run
        self.setWindowTitle("安装 Forge")
        self.setMinimumWidth(620)
        self._task = None
        self._forge_req = ""
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._tick)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(11)

        head = QLabel("为这个服务端目录安装 Forge" if first_run else "Forge 版本")
        head.setObjectName("h3")
        root.addWidget(head)

        intro = QLabel(
            "选一个 Minecraft 版本和对应的 Forge 构建号，程序会自动下载官方安装器并执行 "
            "`--installServer`，把 libraries、启动参数都装好。\n"
            "安装前请确认这个目录是你要用的那个（现在就是面板所在的服务端目录）。"
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        # 当前状态
        box = QFrame()
        box.setObjectName("card")
        g = QGridLayout(box)
        g.setContentsMargins(14, 11, 14, 11)
        g.setVerticalSpacing(6)
        self.lb_current = QLabel("")
        self.lb_java = QLabel("")
        for i, lb in enumerate((self.lb_current, self.lb_java)):
            lb.setObjectName("muted")
            lb.setWordWrap(True)
            g.addWidget(lb, i, 0)
        g.setColumnStretch(0, 1)
        root.addWidget(box)

        # 选择区
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addWidget(QLabel("Minecraft 版本"), 0, 0)
        form.addWidget(QLabel("Forge 版本"), 0, 1)
        self.cb_mc = QComboBox()
        self.cb_mc.setMinimumWidth(180)
        self.cb_mc.currentTextChanged.connect(self._on_mc_changed)
        self.cb_forge = QComboBox()
        self.cb_forge.setMinimumWidth(220)
        form.addWidget(self.cb_mc, 1, 0)
        form.addWidget(self.cb_forge, 1, 1)
        self.btn_refresh = QPushButton("重新获取列表")
        self.btn_refresh.setProperty("cls", "ghost")
        self.btn_refresh.clicked.connect(lambda: self._load_mc(force=True))
        form.addWidget(self.btn_refresh, 1, 2)

        form.addWidget(QLabel("安装源"), 2, 0)
        self.cb_src = QComboBox()
        self.cb_src.addItem("国内镜像 BMCLAPI（推荐，快很多）", "bmcl")
        self.cb_src.addItem("官方源 maven.minecraftforge.net（可能拉一半断掉）", "official")
        form.addWidget(self.cb_src, 3, 0, 1, 2)
        form.setColumnStretch(3, 1)
        root.addLayout(form)

        self.lb_hint = QLabel("")
        self.lb_hint.setObjectName("muted")
        self.lb_hint.setWordWrap(True)
        root.addWidget(self.lb_hint)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        root.addWidget(self.bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("console")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setMinimumHeight(150)
        self.log_view.setVisible(False)
        root.addWidget(self.log_view, 1)

        foot = QHBoxLayout()
        self.lb_state = QLabel("")
        self.lb_state.setObjectName("muted")
        foot.addWidget(self.lb_state, 1)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        self.btn_install = QPushButton("下载并安装")
        self.btn_install.setProperty("cls", "primary")
        self.btn_install.setMinimumWidth(120)
        self.btn_install.clicked.connect(self._start)
        foot.addWidget(self.btn_close)
        foot.addWidget(self.btn_install)
        root.addLayout(foot)

        self._refresh_status()
        self._load_mc()

    # ------------------------------------------------------------ 状态
    def _refresh_status(self):
        info = core.detect_forge()
        if info["kind"]:
            self.lb_current.setText(
                f"当前服务端：已安装 Forge {info['mc']}-{info['forge']}"
                f"（启动方式：{'win_args.txt' if info['kind'] == 'win_args' else info['jar']}）")
        else:
            self.lb_current.setText("当前服务端：没有检测到 Forge（装完就能直接启动）")

        major, line = core.java_version()
        self._java_major = major
        self.lb_java.setText(f"将使用的 Java：{line}（{core.JAVA}）")

    # ------------------------------------------------------------ 版本列表
    def _load_mc(self, force=False):
        self.cb_mc.clear()
        self.cb_mc.addItem("正在获取版本列表…")
        self.cb_mc.setEnabled(False)
        self.btn_install.setEnabled(False)
        self._task = _Task(lambda: core.list_mc_versions(force), self)
        self._task.done.connect(self._mc_loaded)
        self._task.start()

    def _mc_loaded(self, data, err):
        self.cb_mc.setEnabled(True)
        self.cb_mc.clear()
        if err or not data:
            self.cb_mc.addItem("获取失败")
            self.lb_hint.setText(f"连不上版本服务器：{err or '空结果'}\n"
                                 "可以点「重新获取列表」，或直接把 Modrinth/CurseForge 整合包的目录拷过来。")
            return
        cur = core.detect_forge().get("mc") or "1.20.1"
        self.cb_mc.blockSignals(True)          # 填充时别触发一串多余请求
        self.cb_mc.addItems(data)
        idx = self.cb_mc.findText(cur)
        if idx < 0:
            idx = self.cb_mc.findText("1.20.1")
        self.cb_mc.setCurrentIndex(max(0, idx))
        self.cb_mc.blockSignals(False)
        self._on_mc_changed(self.cb_mc.currentText())

    def _on_mc_changed(self, mc):
        if not mc or mc in ("正在获取版本列表…", "获取失败"):
            return
        self._forge_req = mc
        self.cb_forge.clear()
        self.cb_forge.addItem("正在获取…")
        self.cb_forge.setEnabled(False)
        self.btn_install.setEnabled(False)
        need = core.required_java(mc)
        if self._java_major and self._java_major < need:
            self.lb_hint.setText(
                f"⚠ Minecraft {mc} 需要 Java {need} 或更高，当前 Java {self._java_major}，"
                "装上了也启动不了。请先换 Java 再装。")
        else:
            self.lb_hint.setText(f"Minecraft {mc} 需要 Java {need} 或更高（当前满足）。")
        self._task = _Task(lambda: (core.list_forge_builds(mc), core.forge_promos()), self)
        self._task.done.connect(lambda d, e, m=mc: self._forge_loaded(m, d, e))
        self._task.start()

    def _forge_loaded(self, mc, data, err):
        # 用户可能已经切到别的版本，晚到的旧结果直接丢掉
        if mc != getattr(self, "_forge_req", mc) or mc != self.cb_mc.currentText():
            return
        self.cb_forge.setEnabled(True)
        self.cb_forge.clear()
        if err or not data or not data[0]:
            self.cb_forge.addItem("获取失败")
            self.lb_hint.setText(f"这个版本没有取到 Forge 构建：{err or '空结果'}")
            return
        builds, promos = data
        rec = promos.get(f"{mc}-recommended")
        latest = promos.get(f"{mc}-latest")
        for v in builds:
            tag = "（推荐）" if v == rec else ("（最新）" if v == latest else "")
            self.cb_forge.addItem(f"{v}{tag}", v)
        pick = self.cb_forge.findData(rec) if rec else -1
        if pick < 0:
            pick = self.cb_forge.findData(latest) if latest else 0
        self.cb_forge.setCurrentIndex(max(0, pick))
        self.btn_install.setEnabled(not core.FORGEINST.job["running"])
        self.lb_state.setText(f"共 {len(builds)} 个构建" + ("，已标出推荐版" if rec else ""))

    # ------------------------------------------------------------ 安装
    def _start(self):
        mc = self.cb_mc.currentText()
        ver = self.cb_forge.currentData() or self.cb_forge.currentText()
        if not mc or not ver or "获取" in mc or "获取" in str(ver):
            return
        need = core.required_java(mc)
        major, _ = core.java_version()
        if major and major < need:
            QMessageBox.warning(self, "Java 版本不够",
                                f"Minecraft {mc} 需要 Java {need} 或更高，当前是 Java {major}。\n\n"
                                "装了也启动不了，建议先换 Java。")
            return
        r = QMessageBox.question(
            self, "开始安装",
            f"要给这个目录安装 Forge {mc}-{ver} 吗？\n\n{core.BASE}\n\n"
            "安装器会往这个目录写 libraries/、run.bat 等文件，并下载几百 MB 依赖。\n"
            "如果是已有的服，建议先备份存档。")
        if r != QMessageBox.StandardButton.Yes:
            return

        ok, msg = core.FORGEINST.start(mc, ver, self.cb_src.currentData() or "bmcl")
        if not ok:
            QMessageBox.warning(self, "无法开始", msg)
            return
        self.cb_mc.setEnabled(False)
        self.cb_forge.setEnabled(False)
        self.cb_src.setEnabled(False)
        self.btn_install.setEnabled(False)
        self.btn_refresh.setEnabled(False)
        self.bar.setVisible(True)
        self.log_view.setVisible(True)
        self.log_view.clear()
        self.bar.setValue(0)
        self._poll.start(500)

    def _tick(self):
        job = core.FORGEINST.job
        self.bar.setValue(int(job.get("percent", 0)))
        self.lb_state.setText(f"{job.get('phase', '')}：{job.get('message', '')}")
        lines = job.get("lines", [])
        shown = self.log_view.toPlainText().count("\n")
        if len(lines) > shown:
            for line in lines[shown:]:
                self.log_view.appendPlainText(line)
            self.log_view.verticalScrollBar().setValue(
                self.log_view.verticalScrollBar().maximum())
        if not job["running"]:
            self._poll.stop()
            self.cb_mc.setEnabled(True)
            self.cb_forge.setEnabled(True)
            self.cb_src.setEnabled(True)
            self.btn_install.setEnabled(True)
            self.btn_refresh.setEnabled(True)
            self._refresh_status()
            if job.get("error"):
                QMessageBox.critical(self, "安装失败", job["error"])
            else:
                self.bar.setValue(100)
                self.lb_state.setText(job.get("message", "完成"))
                QMessageBox.information(
                    self, "安装完成",
                    f"{job.get('message', '')}\n\n现在可以直接点「启动」开服了。\n"
                    "（如果这个目录照搬自旧服，注意 mods 要换成对应版本的。）")

    def closeEvent(self, e):
        if core.FORGEINST.job["running"]:
            r = QMessageBox.question(self, "安装还没结束",
                                     "安装还在进行，关掉窗口不会中断安装，但看不到进度了。确定关闭？")
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        e.accept()
