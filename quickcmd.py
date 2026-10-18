# -*- coding: utf-8 -*-
"""
一键指令面板 —— 把常用指令做成下拉框 + 快捷按钮，不用背语法。

设计原则：
  1. 每个页签只放这一件事需要的控件，能选就不让打字；
  2. 底部实时显示"即将执行的指令"，用多了自然记住语法；
  3. 破坏性操作（杀实体、清状态）执行前二次确认。
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QCheckBox, QTabWidget, QFrame, QMessageBox, QLineEdit,
)
import json

import core

# ------------------------------------------------------------------ 数据表
STRUCTURES = [
    ("村庄", "village"), ("要塞（末地传送门）", "stronghold"), ("废弃矿井", "mineshaft"),
    ("林地府邸", "mansion"), ("海底神殿", "monument"), ("远古城市", "ancient_city"),
    ("沙漠神殿", "desert_pyramid"), ("丛林神庙", "jungle_temple"), ("沼泽小屋", "swamp_hut"),
    ("雪屋", "igloo"), ("海底废墟", "ocean_ruin"), ("废弃传送门", "ruined_portal"),
    ("沉船", "shipwreck"), ("埋藏的宝藏", "buried_treasure"), ("掠夺者前哨站", "pillager_outpost"),
    ("古迹废墟", "trail_ruins"), ("下界要塞", "fortress"), ("堡垒遗迹", "bastion_remnant"),
    ("末地城", "end_city"),
]

ITEMS = [
    ("钻石", "diamond"), ("下界合金锭", "netherite_ingot"), ("绿宝石", "emerald"),
    ("金锭", "gold_ingot"), ("铁锭", "iron_ingot"), ("钻石剑", "diamond_sword"),
    ("钻石镐", "diamond_pickaxe"), ("附魔金苹果", "enchanted_golden_apple"),
    ("金苹果", "golden_apple"), ("鞘翅", "elytra"), ("不死图腾", "totem_of_undying"),
    ("末影珍珠", "ender_pearl"), ("经验修补瓶", "experience_bottle"), ("下界之星", "nether_star"),
    ("潜影壳", "shulker_shell"), ("烈焰棒", "blaze_rod"), ("红石", "redstone"),
    ("火药", "gunpowder"), ("TNT", "tnt"), ("黑曜石", "obsidian"),
    ("橡木原木", "oak_log"), ("圆石", "cobblestone"), ("熟牛肉", "cooked_beef"),
    ("箭", "arrow"),
]

EFFECTS = [
    ("速度", "speed"), ("力量", "strength"), ("跳跃提升", "jump_boost"),
    ("生命恢复", "regeneration"), ("抗性提升", "resistance"), ("防火", "fire_resistance"),
    ("水下呼吸", "water_breathing"), ("夜视", "night_vision"), ("隐身", "invisibility"),
    ("急迫（挖矿加速）", "haste"), ("生命提升", "health_boost"), ("伤害吸收", "absorption"),
    ("饱和", "saturation"), ("缓慢降落", "slow_falling"), ("海豚的恩惠", "dolphins_grace"),
    ("村庄英雄", "hero_of_the_village"), ("倒霉", "unluck"), ("幸运", "luck"),
    ("发光", "glowing"), ("飘浮", "levitation"), ("失明", "blindness"),
    ("反胃", "nausea"), ("饥饿", "hunger"), ("虚弱", "weakness"),
    ("中毒", "poison"), ("凋零", "wither"), ("缓慢", "slowness"),
    ("挖掘疲劳", "mining_fatigue"), ("黑暗", "darkness"), ("不祥之兆", "bad_omen"),
]

TARGETS = [
    ("所有实体（不含玩家）", "@e[type=!player]"),
    ("所有怪物", "@e[type=!player,type=!item,type=!armor_stand]"),
    ("附近 10 格的所有实体", "@e[distance=..10]"),
    ("所有掉落物", "@e[type=item]"),
    ("僵尸", "@e[type=zombie]"),
    ("骷髅", "@e[type=skeleton]"),
    ("苦力怕", "@e[type=creeper]"),
]

MSG_MODES = [
    ("全服公告（say）", "say"),
    ("全服彩色通知（tellraw）", "tellraw"),
    ("私聊某个玩家（tell）", "tell"),
]

MSG_COLORS = [
    ("黄色（公告）", "yellow"), ("白色", "white"), ("绿色", "green"),
    ("红色（警告）", "red"), ("金色", "gold"), ("浅紫", "light_purple"),
]

MSG_TEMPLATES = [
    ("10 分钟后重启", "服务器将在 10 分钟后重启，请及时回城"),
    ("即将维护", "服务器即将维护，请尽快退出游戏"),
    ("欢迎语", "欢迎来到本服，有问题可以在群里问"),
    ("请勿放岩浆", "请注意：请勿在出生点附近放置岩浆"),
]


def _mc_id(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    return t if ":" in t else f"minecraft:{t}"


def _combo(items, editable=False, width=0):
    cb = QComboBox()
    cb.setEditable(editable)
    for label, value in items:
        cb.addItem(label if not editable else f"{label}  {value}", value)
    if width:
        cb.setMinimumWidth(width)
    return cb


def _val(cb: QComboBox, default="") -> str:
    """
    取控件当前代表的值，三种情况：
      1) 可编辑框里手动打了字   → 用打进去的（取最后一个空格分隔的词，兼容 "标签  id"）
      2) 文本正好等于某个选项   → 用该选项的 data
      3) 普通下拉               → 用 data（注意 data 可能是空串，例如「全部状态」）
    """
    text = cb.currentText().strip()
    if cb.isEditable() and text:
        for i in range(cb.count()):
            if cb.itemText(i) == text:
                d = cb.itemData(i)
                return text if d is None else str(d)   # 玩家名这类没有 data，直接用文本
        return text.split()[-1]
    d = cb.currentData()
    if d is not None:
        return str(d)
    return text or default


def _label(text):
    lb = QLabel(text)
    lb.setObjectName("muted")
    return lb


def _chips(pairs, on_click):
    """一排快捷按钮：点击后把参数填进表单。"""
    lay = QHBoxLayout()
    lay.setSpacing(7)
    cap = QLabel("常用：")
    cap.setObjectName("muted")
    lay.addWidget(cap)
    for label, data in pairs:
        b = QPushButton(label)
        b.setProperty("cls", "chip")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False, d=data: on_click(d))
        lay.addWidget(b)
    lay.addStretch(1)
    return lay


def _select(cb: QComboBox, value: str):
    idx = cb.findData(value)
    if idx >= 0:
        cb.setCurrentIndex(idx)
    else:
        cb.setEditText(value)


class QuickCommandPanel(QWidget):
    """send_cmd(str) 由外部注入，实际动作走 core.SRV.command。"""

    def __init__(self, send_cmd, parent=None):
        super().__init__(parent)
        self.send_cmd = send_cmd
        self._players_sig = ""
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._restore_hint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        f = QFrame()
        f.setObjectName("card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("一键指令")
        title.setObjectName("h3")
        self.hint = QLabel("选好参数后点「执行」")
        self.hint.setObjectName("muted")
        head.addWidget(title)
        head.addWidget(self.hint)
        head.addStretch(1)
        self.btn_exec = QPushButton("执行")
        self.btn_exec.setProperty("cls", "primary")
        self.btn_exec.setMinimumWidth(86)
        self.btn_exec.clicked.connect(self._exec)
        head.addWidget(self.btn_exec)
        lay.addLayout(head)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._tab_locate(), "定位结构")
        self.tabs.addTab(self._tab_give(), "给物品")
        self.tabs.addTab(self._tab_effect(), "给状态")
        self.tabs.addTab(self._tab_clear(), "清状态")
        self.tabs.addTab(self._tab_kill(), "杀实体")
        self.tabs.addTab(self._tab_message(), "发消息")
        self.tabs.currentChanged.connect(self._update)
        lay.addWidget(self.tabs, 1)

        foot = QHBoxLayout()
        lb = QLabel("将执行：")
        lb.setObjectName("muted")
        self.preview = QLabel("")
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        foot.addWidget(lb)
        foot.addWidget(self.preview, 1)
        lay.addLayout(foot)

        root.addWidget(f)
        self._update()

    # ------------------------------------------------------------ 页签容器
    def _page(self, fill):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 8)
        v.setSpacing(9)
        fill(v)
        v.addStretch(1)
        return w

    def _player_combo(self):
        cb = QComboBox()
        cb.setEditable(True)
        cb.setMinimumWidth(132)
        cb.lineEdit().setPlaceholderText("玩家名")
        cb.currentTextChanged.connect(self._update)
        return cb

    # ------------------------------------------------------------ 定位
    def _tab_locate(self):
        def fill(v):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_label("要找什么："))
            self.cb_struct = _combo(STRUCTURES, width=210)
            self.cb_struct.currentIndexChanged.connect(self._update)
            row.addWidget(self.cb_struct)
            tip = QLabel("坐标会输出到控制台，游戏里点聊天框的坐标可以直接传送过去")
            tip.setObjectName("muted")
            row.addWidget(tip)
            row.addStretch(1)
            v.addLayout(row)

            v.addLayout(_chips(
                [("村庄", "village"), ("要塞", "stronghold"), ("远古城市", "ancient_city"),
                 ("末地城", "end_city"), ("下界要塞", "fortress")],
                lambda d: _select(self.cb_struct, d)))
        return self._page(fill)

    # ------------------------------------------------------------ 给物品
    def _tab_give(self):
        def fill(v):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_label("给谁："))
            self.g_player = self._player_combo()
            row.addWidget(self.g_player)
            row.addWidget(_label("物品："))
            self.cb_item = _combo(ITEMS, editable=True, width=210)
            self.cb_item.currentIndexChanged.connect(self._update)
            self.cb_item.editTextChanged.connect(self._update)
            row.addWidget(self.cb_item)
            row.addWidget(_label("数量："))
            self.sp_count = QSpinBox()
            self.sp_count.setRange(1, 9999)
            self.sp_count.setValue(1)
            self.sp_count.valueChanged.connect(self._update)
            row.addWidget(self.sp_count)
            row.addStretch(1)
            v.addLayout(row)

            def pick(pair):
                item, n = pair
                _select(self.cb_item, item)
                self.sp_count.setValue(n)
                self._update()

            v.addLayout(_chips(
                [("钻石 ×64", ("diamond", 64)), ("金苹果 ×16", ("golden_apple", 16)),
                 ("鞘翅", ("elytra", 1)), ("不死图腾", ("totem_of_undying", 1)),
                 ("末影珍珠 ×16", ("ender_pearl", 16))],
                pick))
        return self._page(fill)

    # ------------------------------------------------------------ 给状态
    def _tab_effect(self):
        def fill(v):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_label("给谁："))
            self.e_player = self._player_combo()
            row.addWidget(self.e_player)
            row.addWidget(_label("状态："))
            self.cb_effect = _combo(EFFECTS, width=190)
            self.cb_effect.currentIndexChanged.connect(self._update)
            row.addWidget(self.cb_effect)
            row.addWidget(_label("时长(秒)："))
            self.sp_dur = QSpinBox()
            self.sp_dur.setRange(1, 999999)
            self.sp_dur.setValue(300)
            self.sp_dur.valueChanged.connect(self._update)
            row.addWidget(self.sp_dur)
            row.addWidget(_label("等级："))
            self.sp_level = QSpinBox()
            self.sp_level.setRange(1, 10)
            self.sp_level.setValue(1)
            self.sp_level.valueChanged.connect(self._update)
            row.addWidget(self.sp_level)
            self.cb_hide = QCheckBox("隐藏粒子")
            self.cb_hide.stateChanged.connect(self._update)
            row.addWidget(self.cb_hide)
            row.addStretch(1)
            v.addLayout(row)

            t = QLabel("等级 1 = 状态 I 级；时长按秒算，3600 秒 = 1 小时，999999 ≈ 永久")
            t.setObjectName("muted")
            v.addWidget(t)

            def pick(pair):
                eff, dur, lv = pair
                _select(self.cb_effect, eff)
                self.sp_dur.setValue(dur)
                self.sp_level.setValue(lv)
                self._update()

            v.addLayout(_chips(
                [("夜视 30 分钟", ("night_vision", 1800, 1)),
                 ("力量 II 10 分钟", ("strength", 600, 2)),
                 ("抗性 II 10 分钟", ("resistance", 600, 2)),
                 ("水下呼吸", ("water_breathing", 3600, 1)),
                 ("恢复 II 1 分钟", ("regeneration", 60, 2))],
                pick))
        return self._page(fill)

    # ------------------------------------------------------------ 清状态
    def _tab_clear(self):
        def fill(v):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_label("给谁清："))
            self.c_player = self._player_combo()
            row.addWidget(self.c_player)
            row.addWidget(_label("清哪个："))
            self.cb_clear = _combo([("全部状态", "")] + EFFECTS, width=190)
            self.cb_clear.currentIndexChanged.connect(self._update)
            row.addWidget(self.cb_clear)
            row.addStretch(1)
            v.addLayout(row)

            t = QLabel("服务器开着时，让玩家在游戏里喝牛奶也能清掉全部状态")
            t.setObjectName("muted")
            v.addWidget(t)
        return self._page(fill)

    # ------------------------------------------------------------ 杀实体
    def _tab_kill(self):
        def fill(v):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_label("杀什么："))
            self.cb_target = _combo(TARGETS, editable=True, width=300)
            self.cb_target.currentIndexChanged.connect(self._update)
            self.cb_target.editTextChanged.connect(self._update)
            row.addWidget(self.cb_target)
            row.addStretch(1)
            v.addLayout(row)

            v.addLayout(_chips(
                [("所有掉落物", "@e[type=item]"), ("附近 10 格", "@e[distance=..10]"),
                 ("所有怪物", "@e[type=!player,type=!item,type=!armor_stand]"),
                 ("僵尸", "@e[type=zombie]")],
                lambda d: _select(self.cb_target, d)))

            warn = QLabel("⚠ 「所有实体」「所有怪物」会连带宠物和掉落物一起清掉，执行前会让你再确认一次。")
            warn.setStyleSheet("color: #b7791f; font-size: 12px;")
            v.addWidget(warn)
        return self._page(fill)

    # ------------------------------------------------------------ 发消息
    def _tab_message(self):
        def fill(v):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_label("方式："))
            self.cb_mode = _combo(MSG_MODES, width=184)
            self.cb_mode.currentIndexChanged.connect(self._mode_changed)
            row.addWidget(self.cb_mode)

            row.addWidget(_label("发给："))
            self.msg_player = self._player_combo()
            row.addWidget(self.msg_player)

            row.addWidget(_label("颜色："))
            self.cb_color = _combo(MSG_COLORS, width=118)
            self.cb_color.currentIndexChanged.connect(self._update)
            row.addWidget(self.cb_color)
            row.addStretch(1)
            v.addLayout(row)

            row2 = QHBoxLayout()
            row2.setSpacing(8)
            row2.addWidget(_label("消息："))
            self.msg_text = QLineEdit()
            self.msg_text.setPlaceholderText("要发的内容，例如：今晚 8 点开荒，速来")
            self.msg_text.textChanged.connect(self._update)
            row2.addWidget(self.msg_text, 1)
            v.addLayout(row2)

            def fill_msg(text):
                self.msg_text.setText(text)
                self.msg_text.setFocus()

            v.addLayout(_chips(MSG_TEMPLATES, fill_msg))

            tip = QLabel("say 显示成 [Server] 说话；tellraw 可带颜色；私聊只有目标玩家能看到")
            tip.setObjectName("muted")
            v.addWidget(tip)

            self._mode_changed()
        return self._page(fill)

    def _mode_changed(self, *args):
        mode = _val(self.cb_mode, "say")
        self.msg_player.setEnabled(mode == "tell")
        self.cb_color.setEnabled(mode == "tellraw")
        self._update()

    def _msg_cmd(self):
        msg = self.msg_text.text().strip()
        if not msg:
            return ""
        mode = _val(self.cb_mode, "say")
        if mode == "say":
            return f"say {msg}"
        if mode == "tellraw":
            payload = {"text": msg, "color": _val(self.cb_color, "yellow")}
            return "tellraw @a " + json.dumps(payload, ensure_ascii=False)
        who = _val(self.msg_player)
        return f"tell {who} {msg}" if who else ""

    # ------------------------------------------------------------ 生成指令
    def _players(self):
        return [self.g_player, self.e_player, self.c_player, self.msg_player]

    def _cmd(self):
        idx = self.tabs.currentIndex()
        if idx == 0:
            return f"locate structure {_mc_id(_val(self.cb_struct, 'village'))}"

        if idx == 1:
            who = _val(self.g_player)
            if not who:
                return ""
            return f"give {who} {_mc_id(_val(self.cb_item, 'diamond'))} {self.sp_count.value()}"

        if idx == 2:
            who = _val(self.e_player)
            if not who:
                return ""
            hide = "true" if self.cb_hide.isChecked() else "false"
            return (f"effect give {who} {_mc_id(_val(self.cb_effect, 'speed'))} "
                    f"{self.sp_dur.value()} {self.sp_level.value() - 1} {hide}")

        if idx == 3:
            who = _val(self.c_player)
            if not who:
                return ""
            eff = _val(self.cb_clear, "")
            return f"effect clear {who}" + (f" {_mc_id(eff)}" if eff else "")

        if idx == 4:
            tgt = _val(self.cb_target)
            return f"kill {tgt}" if tgt else ""

        if idx == 5:
            return self._msg_cmd()
        return ""

    def _update(self, *args):
        if getattr(self, "preview", None) is None:   # 页签构造期间还没挂上预览标签
            return
        cmd = self._cmd()
        if not cmd:
            hints = {0: "（选一个结构即可）", 1: "（先选玩家）", 2: "（先选玩家）",
                     3: "（先选玩家）", 4: "（先选目标）", 5: "（先输入消息）"}
            self.preview.setText(hints.get(self.tabs.currentIndex(), "（先填好参数）"))
            self.preview.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 12px; color: #9aa79f;")
            self.btn_exec.setEnabled(False)
            return
        self.preview.setText(cmd)
        self.preview.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; color: #25633f;")
        self.btn_exec.setEnabled(True)

    # ------------------------------------------------------------ 执行
    def _flash(self, text, ok=True):
        self.hint.setText(text)
        self.hint.setStyleSheet(
            f"color: {'#2f7d4f' if ok else '#c0392b'}; font-size: 12px;")
        self._flash_timer.start(2500)

    def _restore_hint(self):
        self.hint.setStyleSheet("")
        self.hint.setText("选好参数后点「执行」")

    def _exec(self):
        cmd = self._cmd()
        if not cmd:
            return
        if not core.SRV.status()["running"]:
            QMessageBox.warning(self, "服务器没运行", "先把服务器启动起来，指令才有地方执行。")
            return

        idx = self.tabs.currentIndex()
        if idx == 4 and cmd.startswith("kill @e"):
            r = QMessageBox.warning(
                self, "确认杀实体",
                f"即将执行：\n\n{cmd}\n\n这会一次清掉范围内所有符合条件的实体，不可撤销。确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
        elif idx == 3:
            r = QMessageBox.question(self, "确认清状态",
                                     f"即将执行：\n\n{cmd}\n\n确定继续？")
            if r != QMessageBox.StandardButton.Yes:
                return

        self.send_cmd(cmd)
        self._flash(f"已发送：{cmd}")

    # ------------------------------------------------------------ 刷新玩家列表
    def refresh_players(self, names):
        names = [n for n in names if n]
        sig = "|".join(sorted(set(names)))
        if sig == self._players_sig:
            return
        self._players_sig = sig
        for cb in self._players():
            cur = cb.currentText().strip()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(names)
            if cur:
                cb.setEditText(cur)
            elif names:
                cb.setCurrentIndex(0)
            cb.blockSignals(False)
        self._update()          # 刷新时屏蔽了信号，这里补一次，否则执行按钮状态会滞后
