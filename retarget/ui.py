"""Chinese in-host retarget workbench. Host work stays on the Qt/Max main thread.

Importing this module does not touch pymxs or create a window. Tests can supply a
plain Session double, and the same widgets run with either Max's PySide edition.
"""
from __future__ import annotations

from contextlib import contextmanager
import time
import math
from .solver import CancelledError

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


def value(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def node_id(node):
    return str(value(node, "id", ""))


def chain_id(chain):
    return str(value(chain, "id", ""))


def dialog_exec(dialog):
    method = getattr(dialog, "exec", None) or dialog.exec_
    return method()


def xyz_quaternion(degrees):
    x, y, z = [math.radians(a) / 2 for a in degrees]
    cx, cy, cz = math.cos(x), math.cos(y), math.cos(z)
    sx, sy, sz = math.sin(x), math.sin(y), math.sin(z)
    return (sx*cy*cz-cx*sy*sz, cx*sy*cz+sx*cy*sz,
            cx*cy*sz-sx*sy*cz, cx*cy*cz+sx*sy*sz)


def quaternion_xyz(quaternion):
    x, y, z, w = quaternion
    norm = math.sqrt(x*x+y*y+z*z+w*w)
    if norm < 1e-12:
        raise ValueError("旋转偏移四元数无效")
    x, y, z, w = x/norm, y/norm, z/norm, w/norm
    return tuple(math.degrees(a) for a in (
        math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)),
        math.asin(max(-1, min(1, 2*(w*y-z*x)))),
        math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))))


STYLE = """
QWidget { color: #24372d; font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif; font-size: 12px; }
QDialog#RetargetWindow, QDialog#ChainEditor { background: #f4f8f4; }
QLabel#heading { font-size: 23px; font-weight: 700; }
QLabel#subtitle, QLabel#help { color: #62766a; }
QLabel#status { background: #e6f3e8; border: 1px solid #c9e3ce; border-radius: 5px; padding: 7px; }
QGroupBox { background: #ffffff; border: 1px solid #d7e3da; border-radius: 6px; margin-top: 12px; padding: 9px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; font-weight: 600; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: white; border: 1px solid #ccdcd0; border-radius: 4px; padding: 5px; min-height: 19px; }
QPushButton { background: #ffffff; border: 1px solid #c9dace; border-radius: 4px; padding: 6px 9px; min-height: 19px; }
QPushButton:hover { background: #eaf5ec; border-color: #8fbc99; }
QPushButton:disabled { color: #97a79b; background: #f0f3f0; }
QPushButton#primary { color: #173f28; background: #a6dfb2; border-color: #81bd8d; font-weight: 600; }
QPushButton#primary:hover { background: #95d7a4; }
QListWidget, QTableWidget, QPlainTextEdit { background: white; border: 1px solid #d2e0d6; border-radius: 4px; selection-background-color: #d8efdf; selection-color: #183d27; }
QHeaderView::section { background: #edf5ee; color: #3e5d49; border: 0; border-bottom: 1px solid #d2e0d6; padding: 8px; font-weight: 600; }
QTableWidget::item:selected { background: #d8efdf; color: #183d27; }
QSplitter::handle { background: #d7e3da; }
QTabWidget::pane { border: 1px solid #d2e0d6; background: white; }
QTabBar::tab { background: #eaf1eb; padding: 7px 15px; }
QTabBar::tab:selected { background: #ffffff; color: #277d42; }
QToolTip { color: #24372d; background: #f7fff8; border: 1px solid #a6c6ad; }
"""


class NoWheelSpinBox(QtWidgets.QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QtWidgets.QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class ChainNodeComboBox(NoWheelComboBox):
    """Search complete paths without using them as the dialog's minimum width."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(18)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.completer().setFilterMode(QtCore.Qt.MatchContains)
        self.completer().setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        for view in (self.view(), self.completer().popup()):
            view.setMinimumWidth(0)
            view.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding)
            view.setTextElideMode(QtCore.Qt.ElideMiddle)
            view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            view.setStyleSheet("QAbstractItemView { background: #ffffff; color: #24372d; "
                              "selection-background-color: #d8efdf; selection-color: #183d27; }")
        self.currentIndexChanged.connect(self._update_tooltip)

    def _update_tooltip(self, *_):
        text = self.currentData(QtCore.Qt.ToolTipRole) or "按名称或完整层级路径搜索节点。"
        self.setToolTip(text)
        self.lineEdit().setToolTip(text)

    def _bound_popup_widths(self):
        width = max(1, self.width())
        self.view().setMaximumWidth(width)
        self.completer().popup().setMaximumWidth(width)
        popup = self.view().window()
        if popup is not self.window():
            popup.setMinimumWidth(0)
            popup.setMaximumWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bound_popup_widths()

    def showPopup(self):
        self._bound_popup_widths()
        super().showPopup()
        self._bound_popup_widths()


def button(text, callback, tooltip="", primary=False):
    widget = QtWidgets.QPushButton(text)
    widget.clicked.connect(callback)
    if tooltip:
        widget.setToolTip(tooltip)
    if primary:
        widget.setObjectName("primary")
    return widget


def integer(minimum=-1000000, maximum=1000000, initial=0):
    widget = NoWheelSpinBox()
    widget.setRange(minimum, maximum)
    widget.setValue(initial)
    return widget


def decimal(minimum=0, maximum=1, initial=1, decimals=3):
    widget = NoWheelDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(minimum, maximum)
    widget.setValue(initial)
    widget.setSingleStep(0.1)
    return widget


def mapping_mode_combo():
    combo = NoWheelComboBox()
    combo.addItem("自动：同数量逐节点；脊柱 / 颈头可重采样", "auto")
    combo.addItem("逐节点：两侧数量相同", "direct")
    combo.addItem("弧长重采样：首尾语义锚点", "resample")
    combo.setToolTip("先分别选完整连续链，按根到末端排列。重采样以首尾对应语义部位为锚点，沿参考世界弧长分配旋转；不复制骨长。")
    return combo


def mapping_state(chain, mode=None):
    source = list(value(chain, "source", []))
    target = list(value(chain, "target", []))
    ns, nt = len(source), len(target)
    counts = f"{ns}→{nt}"
    if not ns or not nt:
        return "待映射 " + counts
    kind = value(chain, "kind", "custom")
    mode = mode or value(chain, "mapping_mode", "auto")
    if kind in ("root", "hips"):
        return ("单节点语义 " if ns == nt == 1 and mode != "resample" else "根 / 骨盆需单对 ") + counts
    resampling = mode == "resample" or (mode == "auto" and ns != nt and kind in ("spine", "neck", "head"))
    if resampling:
        return ("弧长重采样 " if min(ns, nt) >= 2 else "首尾锚点不足 ") + counts
    if ns == nt:
        return "逐节点 " + counts
    return ("逐节点数量不符 " if mode == "direct" else "需指定重采样 ") + counts


class SidePanel(QtWidgets.QGroupBox):
    assignRequested = QtCore.Signal(str, list)
    locateRequested = QtCore.Signal(list)
    captureRequested = QtCore.Signal(str)

    def __init__(self, side, parent=None):
        self.side = side
        self.side_name = "源" if side == "source" else "目标"
        super().__init__(self.side_name + "骨架", parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.capture_button = button("读取 Max 选择", lambda: self.captureRequested.emit(side))
        self.capture_button.setToolTip("先在 Max 选中骨架根或节点；只读取这一侧，不会自动占用视口选择。")
        layout.addWidget(self.capture_button)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("搜索" + self.side_name + "节点 / 层级路径")
        self.search.textChanged.connect(self.filter_nodes)
        layout.addWidget(self.search)
        self.count = QtWidgets.QLabel("尚未读取")
        self.count.setObjectName("help")
        layout.addWidget(self.count)
        self.nodes = QtWidgets.QListWidget()
        self.nodes.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.nodes.itemDoubleClicked.connect(lambda _: self.locateRequested.emit(self.selected_ids()))
        layout.addWidget(self.nodes, 1)
        layout.addWidget(button("填入当前链", lambda: self.assignRequested.emit(side, self.selected_ids()), "按列表中的层级顺序，整体替换当前链的这一侧。"))
        layout.addWidget(button("在 Max 中定位", lambda: self.locateRequested.emit(self.selected_ids()), "这是明确的选择操作，会将视口选择切换为所选节点。"))
        self.setMinimumWidth(150)

    def selected_ids(self):
        return [item.data(QtCore.Qt.UserRole) for item in self.nodes.selectedItems() if not item.isHidden()]

    def refresh(self, nodes):
        selected = set(self.selected_ids())
        self.nodes.clear()
        for node in nodes:
            item = QtWidgets.QListWidgetItem(value(node, "name", node_id(node)))
            item.setData(QtCore.Qt.UserRole, node_id(node))
            path = value(node, "path", "")
            item.setData(QtCore.Qt.UserRole + 1, (str(path) + " " + value(node, "name", "")).casefold())
            kind = value(node, "kind", "未知")
            item.setToolTip(f"{path}\n类型：{kind}\n只读" if not value(node, "writable", True) else f"{path}\n类型：{kind}")
            self.nodes.addItem(item)
            item.setSelected(node_id(node) in selected)
        self.filter_nodes()

    def filter_nodes(self, *_):
        text = self.search.text().casefold().strip()
        visible = 0
        for i in range(self.nodes.count()):
            item = self.nodes.item(i)
            hidden = text not in item.data(QtCore.Qt.UserRole + 1)
            item.setHidden(hidden)
            visible += not hidden
        self.count.setText(f"{self.nodes.count()} 个节点" + (f" · 筛选 {visible}" if text else ""))


class ChainEditor(QtWidgets.QDialog):
    """Ordered full-chain editor; node identity never comes from display names."""
    def __init__(self, session, chain, parent=None):
        super().__init__(parent)
        self.session = session
        self.chain = chain
        self.setObjectName("ChainEditor")
        self.setWindowTitle("编辑整条链 · " + value(chain, "label", chain_id(chain)))
        self.setStyleSheet(STYLE)
        self.setMinimumSize(720, 440)
        self.resize(790, 480)
        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel("两侧各自选择完整连续链，按根 → 末端的直接父子顺序排列。首节点与末节点分别代表同一语义部位；不要按多选顺序猜测。根与骨盆每侧只能一个节点。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.addWidget(QtWidgets.QLabel("链映射模式"))
        self.mapping_mode = mapping_mode_combo()
        mode_index = self.mapping_mode.findData(value(chain, "mapping_mode", "auto"))
        self.mapping_mode.setCurrentIndex(max(0, mode_index))
        if value(chain, "kind", "custom") in ("root", "hips"):
            self.mapping_mode.model().item(self.mapping_mode.findData("resample")).setEnabled(False)
        mode_row.addWidget(self.mapping_mode, 1)
        layout.addLayout(mode_row)
        row = QtWidgets.QHBoxLayout()
        self.lists = {}
        self.candidates = {}
        for side, title in (("source", "源骨架"), ("target", "目标骨架")):
            group = QtWidgets.QGroupBox(title)
            col = QtWidgets.QVBoxLayout(group)
            group.setMinimumWidth(0)
            group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            combo = ChainNodeComboBox()
            for node in getattr(session, side):
                name = str(value(node, "name", node_id(node)))
                path = str(value(node, "path", ""))
                combo.addItem(name + "  ·  " + path, node_id(node))
                combo.setItemData(combo.count()-1, name + "\n" + path, QtCore.Qt.ToolTipRole)
            combo._update_tooltip()
            self.candidates[side] = combo
            col.addWidget(combo)
            addrow = QtWidgets.QHBoxLayout()
            addrow.addWidget(button("添加候选", lambda _=False, s=side: self.add_candidate(s)))
            addrow.addWidget(button("添加 Max 选择", lambda _=False, s=side: self.add_selection(s)))
            col.addLayout(addrow)
            nodes = QtWidgets.QListWidget()
            nodes.setMinimumWidth(0)
            nodes.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding)
            nodes.setTextElideMode(QtCore.Qt.ElideMiddle)
            nodes.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            nodes.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.lists[side] = nodes
            for identity in value(chain, side, []):
                self.add_id(side, identity)
            col.addWidget(nodes, 1)
            actions = QtWidgets.QHBoxLayout()
            actions.addWidget(button("↑", lambda _=False, s=side: self.move(s, -1)))
            actions.addWidget(button("↓", lambda _=False, s=side: self.move(s, 1)))
            actions.addWidget(button("移除所选", lambda _=False, s=side: self.remove(s)))
            col.addLayout(actions)
            row.addWidget(group, 1)
        layout.addLayout(row, 1)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch()
        footer.addWidget(button("取消", self.reject))
        footer.addWidget(button("应用链映射", self.validate_and_accept, primary=True))
        layout.addLayout(footer)

    def add_id(self, side, identity):
        identity = str(identity)
        widget = self.lists[side]
        if identity in self.ids(side):
            return
        nodes = {node_id(n): n for n in getattr(self.session, side)}
        node = nodes.get(identity)
        item = QtWidgets.QListWidgetItem(value(node, "name", "失效节点：" + identity))
        item.setData(QtCore.Qt.UserRole, identity)
        item.setToolTip(str(value(node, "path", identity)))
        widget.addItem(item)

    def ids(self, side):
        widget = self.lists[side]
        return [widget.item(i).data(QtCore.Qt.UserRole) for i in range(widget.count())]

    def add_candidate(self, side):
        combo = self.candidates[side]
        # Editable text is a search aid, never a free-form identity.
        if combo.currentIndex() >= 0 and combo.currentText() == combo.itemText(combo.currentIndex()):
            self.add_id(side, combo.currentData())

    def add_selection(self, side):
        try:
            allowed = {node_id(n) for n in getattr(self.session, side)}
            picked = [str(i) for i in self.session.host.selection_ids()]
            for identity in picked:
                if identity in allowed:
                    self.add_id(side, identity)
            rejected = len([i for i in picked if i not in allowed])
            self.message.setText(f"忽略 {rejected} 个不属于这一侧的节点。" if rejected else "已添加所选节点；请核对顺序。")
        except Exception as error:
            self.message.setText("读取选择失败：" + str(error))

    def move(self, side, direction):
        widget = self.lists[side]
        rows = sorted((widget.row(i) for i in widget.selectedItems()), reverse=direction > 0)
        for index in rows:
            target = index + direction
            if 0 <= target < widget.count():
                item = widget.takeItem(index)
                widget.insertItem(target, item)
                item.setSelected(True)

    def remove(self, side):
        widget = self.lists[side]
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    def validate_and_accept(self):
        for side in ("source", "target"):
            nodes = {node_id(n): n for n in getattr(self.session, side)}
            identities = self.ids(side)
            if any(identity not in nodes for identity in identities):
                self.message.setText("链中存在失效节点，请重新选择。")
                return
            for parent, child in zip(identities, identities[1:]):
                if str(value(nodes[child], "parent", "")) != parent:
                    self.message.setText(("源" if side == "source" else "目标") + "链必须按直接父子顺序排列，请用 ↑ ↓ 调整并补齐中间节点。")
                    return
        source, target = self.ids("source"), self.ids("target")
        if source and target:
            kind = value(self.chain, "kind", "custom")
            mode = self.mapping_mode.currentData()
            if kind in ("root", "hips") and (len(source) != 1 or len(target) != 1 or mode == "resample"):
                self.message.setText("根与骨盆是独立的单节点语义，每侧只能选择一个节点，不进行链重采样。")
                return
            is_resample = mode == "resample" or (mode == "auto" and len(source) != len(target) and kind in ("spine", "neck", "head"))
            if is_resample and min(len(source), len(target)) < 2:
                self.message.setText("弧长重采样需要两侧各至少两个节点，首末节点需有相同语义。")
                return
            if len(source) != len(target) and not is_resample:
                self.message.setText("当前模式需要相同节点数量；连续链可明确选择“弧长重采样”。")
                return
        self.accept()


class SuggestionDialog(QtWidgets.QDialog):
    def __init__(self, suggestions, chains, name_lookup, parent=None):
        super().__init__(parent)
        self.setWindowTitle("确认自动匹配建议")
        self.resize(960, 420)
        self.suggestions = list(suggestions)
        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel("名称匹配只提供候选。请检查左右、层级和链顺序；仅应用勾选项，未勾选项保留原映射。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QtWidgets.QTableWidget(len(self.suggestions), 6)
        self.table.setHorizontalHeaderLabels(["采用", "关键链", "源节点", "目标节点", "置信", "原因"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        labels = {chain_id(c): value(c, "label", chain_id(c)) for c in chains}
        for row, suggestion in enumerate(self.suggestions):
            check = QtWidgets.QTableWidgetItem()
            check.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            check.setCheckState(QtCore.Qt.Unchecked)
            self.table.setItem(row, 0, check)
            confidence = float(value(suggestion, "confidence", 0))
            if confidence <= 1:
                confidence *= 100
            cells = [labels.get(str(value(suggestion, "chain_id", "")), str(value(suggestion, "chain_id", ""))),
                     " → ".join(name_lookup("source", i) for i in value(suggestion, "source", [])),
                     " → ".join(name_lookup("target", i) for i in value(suggestion, "target", [])),
                     f"{confidence:.0f}%", str(value(suggestion, "reason", ""))]
            for column, cell in enumerate(cells, 1):
                item = QtWidgets.QTableWidgetItem(cell)
                item.setToolTip(cell)
                self.table.setItem(row, column, item)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table, 1)
        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(button("全选", lambda: self.check_all(True)))
        footer.addWidget(button("全不选", lambda: self.check_all(False)))
        footer.addStretch()
        footer.addWidget(button("取消", self.reject))
        footer.addWidget(button("应用勾选建议", self.accept, primary=True))
        layout.addLayout(footer)

    def check_all(self, checked):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)

    def chosen(self):
        return [candidate for row, candidate in enumerate(self.suggestions)
                if self.table.item(row, 0).checkState() == QtCore.Qt.Checked]


class RebindDialog(QtWidgets.QDialog):
    """Every changed/ambiguous portable identity needs an explicit user choice."""
    def __init__(self, session, unresolved, parent=None):
        super().__init__(parent)
        self.setWindowTitle("预设节点重绑定")
        self.resize(950, 420)
        self.unresolved = list(unresolved)
        self.combos = []
        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel("预设节点不会按同名任意绑定。逐项选择当前场景节点；可保留待绑定，但未解决前不能预览或烘焙。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QtWidgets.QTableWidget(len(self.unresolved), 4)
        self.table.setHorizontalHeaderLabels(["归属", "预设节点", "当前场景节点（明确选择）", "原因"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        for row, issue in enumerate(self.unresolved):
            side = value(issue, "side", "source")
            label = "源骨架" if side == "source" else "目标骨架"
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(label))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(value(issue, "name", value(issue, "preset_id", "")))))
            combo = NoWheelComboBox()
            combo.addItem("— 保持待绑定 —", None)
            suggested = {str(i) for i in value(issue, "candidates", [])}
            for node in getattr(session, side):
                identity = node_id(node)
                suffix = " · 建议候选" if identity in suggested else ""
                combo.addItem(value(node, "name", identity) + "  ·  " + str(value(node, "path", identity)) + suffix, identity)
            combo.setToolTip("列表包含这一侧全部已读取节点。候选只是线索，不会自动选中。")
            self.table.setCellWidget(row, 2, combo)
            self.combos.append(combo)
            reason = str(value(issue, "reason", "需要手动确认身份"))
            item = QtWidgets.QTableWidgetItem(reason)
            item.setToolTip(reason)
            self.table.setItem(row, 3, item)
            self.table.setRowHeight(row, 44)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table, 1)
        self.message = QtWidgets.QLabel("")
        layout.addWidget(self.message)
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch()
        footer.addWidget(button("稍后处理", self.reject))
        footer.addWidget(button("应用明确绑定", self.validate_and_accept, primary=True))
        layout.addLayout(footer)

    def bindings(self):
        result = {"source": {}, "target": {}}
        for issue, combo in zip(self.unresolved, self.combos):
            identity = combo.currentData()
            if identity is not None:
                result[value(issue, "side", "source")][str(value(issue, "preset_id", ""))] = str(identity)
        return result["source"], result["target"]

    def validate_and_accept(self):
        source, target = self.bindings()
        for bindings in (source, target):
            if len(set(bindings.values())) != len(bindings):
                self.message.setText("同一侧的两个预设节点不能绑定到同一个当前节点，请检查选择。")
                return
        self.accept()


class RetargetWindow(QtWidgets.QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._busy = False
        self._cancel = False
        self._preview_valid = False
        self._overrides = {}
        self._unresolved = []
        self._last_chain_id = None
        self.setObjectName("RetargetWindow")
        self.setWindowTitle("LX 双骨架重定向")
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(1220, 850)
        self.setMinimumSize(900, 680)
        self.setStyleSheet(STYLE)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(16, 13, 16, 12)
        self.content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        titlebar = QtWidgets.QHBoxLayout()
        heading = QtWidgets.QLabel("双骨架重定向")
        heading.setObjectName("heading")
        titlebar.addWidget(heading)
        titlebar.addStretch()
        self.rebind_button = button("处理待重绑定", self.rebind_presets)
        self.rebind_button.setEnabled(False)
        titlebar.addWidget(self.rebind_button)
        titlebar.addWidget(button("加载预设", self.load_preset))
        titlebar.addWidget(button("保存预设", self.save_preset))
        layout.addLayout(titlebar)
        subtitle = QtWidgets.QLabel("源与目标同时保留在场景 · 先读取两侧，再配置关键链和参考姿态")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        host_label = getattr(session.host, "instance_label", None) or getattr(session.host, "name", None)
        if callable(host_label):
            host_label = host_label()
        self.instance = QtWidgets.QLabel("当前 Max 实例：" + str(host_label or "由此窗口所在宿主确定，不自动切换实例"))
        self.instance.setObjectName("help")
        layout.addWidget(self.instance)
        top = QtWidgets.QHBoxLayout()
        self.include_children = QtWidgets.QCheckBox("读取时包含所选节点的子级")
        self.include_children.setMinimumWidth(270)
        self.include_children.setChecked(True)
        top.addWidget(self.include_children)
        top.addStretch()
        self.chain_filter = QtWidgets.QLineEdit()
        self.chain_filter.setMaximumWidth(300)
        self.chain_filter.setPlaceholderText("筛选关键链 / 已映射节点")
        self.chain_filter.textChanged.connect(self.filter_chains)
        top.addWidget(self.chain_filter)
        layout.addLayout(top)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.side_panels = {}
        source = self._side_panel("source")
        target = self._side_panel("target")
        self.splitter.addWidget(source)
        self.splitter.addWidget(self._mapping_panel())
        self.splitter.addWidget(target)
        self.splitter.setSizes([200, 750, 200])
        layout.addWidget(self.splitter, 5)
        layout.addWidget(self._visibility_panel())
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._basic_panel(), "基础设置")
        self.tabs.addTab(self._advanced_panel(), "按链高级设置")
        self.tabs.addTab(self._report_panel(), "预检与操作记录")
        self.tabs.setMaximumHeight(245)
        layout.addWidget(self.tabs, 2)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(button("预检", self.preflight))
        actions.addWidget(button("预览当前帧", self.preview))
        actions.addWidget(button("恢复预览", self.restore_preview))
        actions.addWidget(button("恢复上次烘焙", self.restore_last_bake, "恢复本会话上次成功烘焙之前的数据。重新烘焙会更新恢复点。"))
        actions.addStretch()
        self.bake_button = button("烘焙到目标", self.bake, primary=True)
        actions.addWidget(self.bake_button)
        layout.addLayout(actions)
        outer.addWidget(self.content, 1)
        self.status = QtWidgets.QLabel("尚未预览。请读取源骨架与目标骨架，并分别记录参考姿态。")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        initial_settings = getattr(session, "settings", {})
        if isinstance(initial_settings, dict) and initial_settings:
            self._load_settings(initial_settings)
        self.refresh()
        self._connect_settings()

    def _side_panel(self, side):
        panel = SidePanel(side)
        panel.captureRequested.connect(self.capture)
        panel.assignRequested.connect(self.assign)
        panel.locateRequested.connect(self.locate)
        self.side_panels[side] = panel
        return panel

    def _mapping_panel(self):
        group = QtWidgets.QGroupBox("关键链对应 · 左侧是源，右侧是目标")
        layout = QtWidgets.QVBoxLayout(group)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(button("自动匹配建议", self.suggest))
        row.addWidget(button("编辑整条链", self.edit_chain))
        row.addWidget(button("添加自定义链", self.add_chain))
        row.addWidget(button("移除当前链", self.remove_chain))
        layout.addLayout(row)
        self.mapping = QtWidgets.QTableWidget(0, 3)
        self.mapping.setHorizontalHeaderLabels(["源骨架 · 根 → 末端", "关键链 / 状态", "目标骨架 · 根 → 末端"])
        self.mapping.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.mapping.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.mapping.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.mapping.setWordWrap(False)
        self.mapping.verticalHeader().hide()
        self.mapping.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.mapping.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.mapping.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.mapping.itemDoubleClicked.connect(lambda _: self.edit_chain())
        self.mapping.itemSelectionChanged.connect(self.chain_changed)
        layout.addWidget(self.mapping, 1)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(button("拾取源选择", lambda: self.pick("source"), "将 Max 当前选择填入源侧，自动排除非源节点。"))
        row.addWidget(button("清空源", lambda: self.assign("source", [])))
        row.addStretch()
        row.addWidget(button("镜像到对侧链", self.mirror_suggestion, "以左右名称生成对侧链候选；需确认，不执行几何镜像。"))
        row.addStretch()
        row.addWidget(button("清空目标", lambda: self.assign("target", [])))
        row.addWidget(button("拾取目标选择", lambda: self.pick("target")))
        layout.addLayout(row)
        return group

    def _visibility_panel(self):
        group = QtWidgets.QGroupBox("视口显隐 · 仅作用于已读取的两侧节点")
        layout = QtWidgets.QHBoxLayout(group)
        for label, action in (("显示源", "show_source"), ("隐藏源", "hide_source"),
                              ("显示目标", "show_target"), ("隐藏目标", "hide_target"),
                              ("显示全部", "show_all"), ("仅看源", "only_source"),
                              ("仅看目标", "only_target"), ("仅看当前链", "only_chain")):
            layout.addWidget(button(label, lambda _=False, a=action: self.visibility(a)))
        layout.addStretch()
        layout.addWidget(button("恢复进入前状态", self.restore_visibility, "精确恢复会话影响过的节点；不使用 Unhide All，不揭开共层无关对象。"))
        return group

    def _basic_panel(self):
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(widget)
        self.reference_frame = integer(initial=self.current_frame())
        self.reference_frame.setToolTip("参考姿态以明确的整数帧记录；预览使用当前完整时间（包含子帧）。")
        grid.addWidget(QtWidgets.QLabel("参考姿态帧"), 0, 0)
        grid.addWidget(self.reference_frame, 0, 1)
        grid.addWidget(button("取当前帧", lambda: self.reference_frame.setValue(self.current_frame())), 0, 2)
        self.source_ref = button("记录源参考姿态", lambda: self.reference("source"))
        self.target_ref = button("记录目标参考姿态", lambda: self.reference("target"))
        grid.addWidget(self.source_ref, 0, 3)
        grid.addWidget(self.target_ref, 0, 4)
        self.root_mode = NoWheelComboBox()
        for label, key in (("全局位移与旋转", "global"), ("原地（固定根位置）", "in_place"), ("水平位移与朝向", "horizontal")):
            self.root_mode.addItem(label, key)
        self.root_mode.setToolTip("根与骨盆分别映射。根运动仅控制根链；目标子骨默认保留自身参考骨长。")
        grid.addWidget(QtWidgets.QLabel("根运动"), 1, 0)
        grid.addWidget(self.root_mode, 1, 1, 1, 2)
        self.scale_mode = NoWheelComboBox()
        for label, key in (("按参考骨架比例", "auto"), ("不缩放位移", "none"), ("手动比例", "manual")):
            self.scale_mode.addItem(label, key)
        self.scale = decimal(0.001, 1000, 1)
        self.scale.setEnabled(False)
        grid.addWidget(self.scale_mode, 1, 3)
        grid.addWidget(self.scale, 1, 4)
        self.start = integer(initial=0)
        self.end = integer(initial=100)
        try:
            bounds = self.session.host.frame_range()
            self.start.setValue(int(bounds[0]))
            self.end.setValue(int(bounds[1]))
        except (AttributeError, TypeError):
            pass
        self.step = integer(1, 1000, 1)
        range_row = QtWidgets.QHBoxLayout()
        for label, control in (("从", self.start), ("到", self.end), ("步长", self.step)):
            range_row.addWidget(QtWidgets.QLabel(label))
            range_row.addWidget(control)
        grid.addWidget(QtWidgets.QLabel("烘焙范围"), 2, 0)
        grid.addLayout(range_row, 2, 1, 1, 2)
        self.output_mode = NoWheelComboBox()
        self.output_mode.addItem("已有目标关键帧时拒绝（推荐）", "reject_existing")
        self.output_mode.addItem("覆盖区间内关键帧", "replace_range")
        self.output_mode.addItem("Biped 新动画层（保留基础轨）", "new_layer")
        self.output_mode.setToolTip("覆盖区间保留区间外键，但边界切线可能影响邻接区间；请先保存场景。")
        grid.addWidget(self.output_mode, 2, 3, 1, 2)
        self.reference_info = QtWidgets.QLabel("参考姿态独立记录，不需要在场景里强制摆成同一姿势。")
        self.reference_info.setObjectName("help")
        self.reference_info.setWordWrap(True)
        grid.addWidget(self.reference_info, 3, 0, 1, 5)
        boundary_info = QtWidgets.QLabel("烘焙在范围前后各加 1 帧原姿态保护键；边界附近插值可能变化。")
        boundary_info.setObjectName("help")
        boundary_info.setWordWrap(True)
        grid.addWidget(boundary_info, 4, 0, 1, 5)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        return widget

    def _advanced_panel(self):
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(widget)
        self.override_label = QtWidgets.QLabel("先选中一条关键链")
        grid.addWidget(self.override_label, 0, 0, 1, 4)
        self.mapping_mode = mapping_mode_combo()
        grid.addWidget(QtWidgets.QLabel("链映射模式"), 1, 0)
        grid.addWidget(self.mapping_mode, 1, 1, 1, 4)
        self.rotation_weight = decimal(initial=1)
        self.translation_weight = decimal(initial=0)
        self.rotation_weight.setToolTip("0 保留目标参考姿态，1 完整转移参考姿态上的旋转变化。")
        self.translation_weight.setToolTip("普通子链默认 0，保留骨长；根运动由基础设置控制。仅支持适配器允许的平移。")
        grid.addWidget(QtWidgets.QLabel("旋转权重"), 2, 0)
        grid.addWidget(self.rotation_weight, 2, 1)
        grid.addWidget(QtWidgets.QLabel("平移权重"), 2, 2)
        grid.addWidget(self.translation_weight, 2, 3)
        grid.addWidget(button("恢复当前链默认", self.reset_chain_settings), 2, 4)
        grid.addWidget(QtWidgets.QLabel("局部旋转修正"), 3, 0)
        angles = QtWidgets.QHBoxLayout()
        self.rotation_offsets = []
        for axis in ("X", "Y", "Z"):
            spin = decimal(-360, 360, 0, decimals=2)
            spin.setSuffix("°")
            spin.setToolTip("在求解后的目标局部空间依次施加 XYZ 旋转修正；仅修改会话设置。")
            angles.addWidget(QtWidgets.QLabel(axis))
            angles.addWidget(spin)
            self.rotation_offsets.append(spin)
        grid.addLayout(angles, 3, 1, 1, 4)
        note = QtWidgets.QLabel("重采样：两侧连续链各至少两节点，首尾语义对应，按参考世界弧长分配旋转；重采样时平移权重须为 0。根 / 骨盆始终单对。\nFK、IK / 足底接触保持、Biped / CAT 分别适配验收；未验证能力不因 FK 可用而视为支持。")
        note.setWordWrap(True)
        note.setObjectName("help")
        grid.addWidget(note, 4, 0, 1, 5)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setRowStretch(5, 1)
        return widget

    def _report_panel(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        self.report = QtWidgets.QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumBlockCount(600)
        self.report.setPlaceholderText("预检问题、待重绑定节点、烘焙摘要和恢复结果会显示在这里。")
        layout.addWidget(self.report)
        return widget

    def _connect_settings(self):
        for spin in (self.reference_frame, self.start, self.end, self.step, self.scale):
            spin.valueChanged.connect(self.settings_changed)
        for combo in (self.root_mode, self.scale_mode, self.output_mode):
            combo.currentIndexChanged.connect(self.settings_changed)
        self.rotation_weight.valueChanged.connect(self.chain_settings_changed)
        self.translation_weight.valueChanged.connect(self.chain_settings_changed)
        self.mapping_mode.currentIndexChanged.connect(self.chain_settings_changed)
        for spin in self.rotation_offsets:
            spin.valueChanged.connect(self.chain_settings_changed)

    def current_frame(self):
        try:
            return int(self.session.host.current_frame())
        except Exception:
            return 0

    def current_chain(self):
        row = self.mapping.currentRow()
        if row < 0 or self.mapping.item(row, 1) is None:
            return None
        identity = self.mapping.item(row, 1).data(QtCore.Qt.UserRole)
        return next((c for c in self.session.chains if chain_id(c) == identity), None)

    def name(self, side, identity):
        identity = str(identity)
        return next((value(n, "name", identity) for n in getattr(self.session, side) if node_id(n) == identity), "失效：" + identity)

    def refresh(self):
        current = chain_id(self.current_chain()) if self.current_chain() else self._last_chain_id
        for side in ("source", "target"):
            self.side_panels[side].refresh(getattr(self.session, side))
        self.mapping.blockSignals(True)
        self.mapping.setRowCount(len(self.session.chains))
        selected_row = 0
        for row, chain in enumerate(self.session.chains):
            source = list(value(chain, "source", []))
            target = list(value(chain, "target", []))
            mode = self._overrides.get(chain_id(chain), {}).get("mapping_mode", value(chain, "mapping_mode", "auto"))
            state = mapping_state(chain, mode)
            cells = [" → ".join(self.name("source", i) for i in source) or "— 请选择源节点 —",
                     value(chain, "label", chain_id(chain)) + f"\n{state}",
                     " → ".join(self.name("target", i) for i in target) or "— 请选择目标节点 —"]
            for column, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(text)
                item.setData(QtCore.Qt.UserRole, chain_id(chain))
                self.mapping.setItem(row, column, item)
            self.mapping.setRowHeight(row, 51)
            if chain_id(chain) == current:
                selected_row = row
        self.mapping.blockSignals(False)
        if self.mapping.rowCount():
            self.mapping.selectRow(selected_row)
        self.filter_chains()
        self.chain_changed()

    def filter_chains(self, *_):
        text = self.chain_filter.text().casefold().strip()
        visible = []
        for row in range(self.mapping.rowCount()):
            haystack = " ".join(self.mapping.item(row, col).text() for col in range(3)).casefold()
            hidden = text not in haystack
            self.mapping.setRowHidden(row, hidden)
            if not hidden:
                visible.append(row)
        current = self.mapping.currentRow()
        if visible and current not in visible:
            self.mapping.selectRow(visible[0])
        elif not visible:
            self.mapping.clearSelection()
            self.mapping.setCurrentCell(-1, -1)

    def log(self, message):
        self.report.appendPlainText(str(message))

    def notify(self, message, error=False):
        prefix = "操作未完成：" if error else ""
        self.status.setText(prefix + str(message))
        self.log(prefix + str(message))
        if error:
            self.tabs.setCurrentIndex(2)

    def run(self, label, callback, changed=False):
        if self._busy:
            return None
        try:
            if changed:
                self.invalidate_preview()
            result = callback()
            self.refresh()
            self.notify(label)
            return result
        except Exception as error:
            self.notify(f"{label}失败；{error}", error=True)
            return None

    def invalidate_preview(self):
        # Restore before changing a mapping/reference/settings. A failed restore
        # propagates and prevents the dependent mutation.
        if self._preview_valid:
            self.session.restore_preview()
            self._preview_valid = False

    def settings_changed(self, *_):
        if self._busy:
            return
        self.scale.setEnabled(self.scale_mode.currentData() == "manual")
        try:
            was_valid = self._preview_valid
            self.invalidate_preview()
            self.status.setText("设置已改变；已恢复旧预览，请重新预览。" if was_valid else "设置已改变；请预检并重新预览。")
        except Exception as error:
            self.notify("旧预览恢复失败：" + str(error), error=True)

    def chain_changed(self):
        chain = self.current_chain()
        self._last_chain_id = chain_id(chain) if chain else None
        if not hasattr(self, "rotation_weight"):
            return
        self.override_label.setText("当前链：" + value(chain, "label", chain_id(chain)) if chain else "先选中一条关键链")
        settings = self._overrides.get(self._last_chain_id, {})
        mode = settings.get("mapping_mode", value(chain, "mapping_mode", "auto"))
        self.mapping_mode.blockSignals(True)
        self.mapping_mode.setCurrentIndex(max(0, self.mapping_mode.findData(mode)))
        self.mapping_mode.setEnabled(chain is not None)
        self.mapping_mode.model().item(self.mapping_mode.findData("resample")).setEnabled(value(chain, "kind", "custom") not in ("root", "hips"))
        self.mapping_mode.blockSignals(False)
        for spin, key, default in ((self.rotation_weight, "rotation_weight", 1), (self.translation_weight, "translation_weight", 0)):
            spin.blockSignals(True)
            spin.setValue(settings.get(key, default))
            spin.setEnabled(chain is not None)
            spin.blockSignals(False)
        angles = quaternion_xyz(settings.get("offset", (0, 0, 0, 1)))
        for spin, angle in zip(self.rotation_offsets, angles):
            spin.blockSignals(True)
            spin.setValue(angle)
            spin.setEnabled(chain is not None)
            spin.blockSignals(False)

    def chain_settings_changed(self, *_):
        chain = self.current_chain()
        if chain:
            self._overrides[chain_id(chain)] = {"rotation_weight": self.rotation_weight.value(),
                "translation_weight": self.translation_weight.value(),
                "offset": xyz_quaternion([spin.value() for spin in self.rotation_offsets]),
                "mapping_mode": self.mapping_mode.currentData()}
            self.settings_changed()
            row = self.mapping.currentRow()
            if row >= 0 and self.mapping.item(row, 1) is not None:
                text = value(chain, "label", chain_id(chain)) + "\n" + mapping_state(chain, self.mapping_mode.currentData())
                self.mapping.item(row, 1).setText(text)
                self.mapping.item(row, 1).setToolTip(text)

    def reset_chain_settings(self):
        chain = self.current_chain()
        if chain:
            self._overrides[chain_id(chain)] = {"rotation_weight": 1, "translation_weight": 0,
                "offset": (0, 0, 0, 1), "mapping_mode": "auto"}
            self.chain_changed()
            self.chain_settings_changed()

    def settings(self):
        return {"root_mode": self.root_mode.currentData(), "scale_mode": self.scale_mode.currentData(),
                "scale": self.scale.value(), "rotation_weight": 1.0, "translation_weight": 0.0,
                "output_mode": self.output_mode.currentData(), "chain_overrides": dict(self._overrides),
                "start": self.start.value(), "end": self.end.value(), "step": self.step.value(),
                "reference_frame": self.reference_frame.value()}

    def sync_settings(self):
        if hasattr(self.session, "set_settings"):
            self.session.set_settings(self.settings())
        else:
            self.session.settings = self.settings()

    def capture(self, side):
        def action():
            result = self.session.capture(side, include_children=self.include_children.isChecked())
            (self.source_ref if side == "source" else self.target_ref).setText("记录" + ("源" if side == "source" else "目标") + "参考姿态")
            if self._unresolved:
                self._set_unresolved([])
            return result
        result = self.run("已读取" + ("源" if side == "source" else "目标") + "骨架；请重新记录这一侧参考姿态。",
                          action, changed=True)
        return result

    def assign(self, side, ids):
        chain = self.current_chain()
        if not chain:
            self.notify("请先选择关键链。", error=True)
            return
        if ids is None:
            ids = []
        return self.run("已更新链映射。", lambda: self.session.assign(chain_id(chain), side, ids), changed=True)

    def pick(self, side):
        try:
            ids = [str(i) for i in self.session.host.selection_ids()]
            allowed = {node_id(n) for n in getattr(self.session, side)}
            invalid = [i for i in ids if i not in allowed]
            if invalid:
                raise ValueError("选择中有不属于这一侧的节点，请先读取骨架或重新选择。")
            self.assign(side, ids)
        except Exception as error:
            self.notify(str(error), error=True)

    def locate(self, ids):
        if not ids:
            self.notify("请先在节点列表中选中要定位的节点。", error=True)
            return
        self.run("已在 Max 中定位所选节点。", lambda: self.session.select_nodes(ids))

    def edit_chain(self):
        chain = self.current_chain()
        if chain is None:
            return
        dialog = ChainEditor(self.session, chain, self)
        current_mode = self._overrides.get(chain_id(chain), {}).get("mapping_mode", value(chain, "mapping_mode", "auto"))
        dialog.mapping_mode.setCurrentIndex(max(0, dialog.mapping_mode.findData(current_mode)))
        if dialog_exec(dialog) != QtWidgets.QDialog.Accepted:
            return
        source, target = dialog.ids("source"), dialog.ids("target")
        def action():
            result = self._apply_mapping_batch([{"chain_id": chain_id(chain), "source": source, "target": target}])
            overrides = dict(self._overrides.get(chain_id(chain), {}))
            overrides["mapping_mode"] = dialog.mapping_mode.currentData()
            self._overrides[chain_id(chain)] = overrides
            self.sync_settings()
            return result
        self.run("已应用整条语义链映射与模式。", action, changed=True)

    def add_chain(self):
        name, accepted = QtWidgets.QInputDialog.getText(self, "添加自定义链", "链名称（例如：尾巴、左手食指）")
        if accepted and name.strip():
            self.run("已添加自定义链。", lambda: self.session.add_chain(name.strip(), "custom"), changed=True)

    def remove_chain(self):
        chain = self.current_chain()
        if chain:
            self.run("已移除当前链；场景节点不会被删除。", lambda: self.session.remove_chain(chain_id(chain)), changed=True)

    def reference(self, side):
        frame = self.reference_frame.value()
        def action():
            result = self.session.reference(side, frame)
            (self.source_ref if side == "source" else self.target_ref).setText(("源" if side == "source" else "目标") + f"参考 ✓ 帧 {frame}")
            return result
        result = self.run(f"已记录{'源' if side == 'source' else '目标'}参考姿态 · 帧 {frame}；场景姿态未被修改。",
                          action, changed=True)
        return result

    def visibility(self, action):
        chain = self.current_chain()
        if action == "only_chain" and not chain:
            self.notify("请先选中关键链。", error=True)
            return
        result = self.run("已更新会话节点显隐；层与类别隐藏以宿主反馈为准。",
                          lambda: self.session.visibility(action, chain_id(chain) if chain else None), changed=True)
        if result:
            self.log(str(result))

    def restore_visibility(self):
        missing = self.run("已恢复会话影响过的节点显隐。", self.session.restore_visibility)
        if missing:
            self.notify(f"已恢复仍有效节点的显隐；{len(missing)} 个节点已失效，无法恢复。")

    def preflight(self):
        def action():
            self.sync_settings()
            issues = self.session.preflight()
            self.log("\n预检结果")
            if not issues:
                self.log("未发现阻断问题；兼容性仍以实际宿主验证范围为准。")
            for issue in issues or []:
                severity = str(value(issue, "severity", "info"))
                labels = {"error": "必须修复", "warning": "建议处理", "info": "说明"}
                self.log(f"[{labels.get(severity, severity)}] {value(issue, 'message', str(issue))}")
            return issues
        result = self.run("预检完成，请查看具体问题。", action, changed=True)
        self.tabs.setCurrentIndex(2)
        return result

    def _apply_mapping_batch(self, suggestions):
        suggestions = list(suggestions)
        explicit_modes = {}
        missing = object()
        for row in suggestions:
            mode = value(row, "mapping_mode", missing)
            if mode is not missing:
                if mode not in ("auto", "direct", "resample"):
                    raise ValueError("候选链映射模式无效，请重新生成建议。")
                explicit_modes[str(value(row, "chain_id"))] = mode

        def remember_confirmed_modes():
            # The UI may still contain a legacy 'direct' override. Once a user
            # explicitly confirms a resampling suggestion, its mode must become
            # the UI setting as well; otherwise the next preflight/save would
            # silently push the stale override back into the Session.
            for identity, mode in explicit_modes.items():
                overrides = dict(self._overrides.get(identity, {}))
                overrides["mapping_mode"] = mode
                self._overrides[identity] = overrides

        if hasattr(self.session, "apply_suggestions"):
            result = self.session.apply_suggestions(suggestions)
            remember_confirmed_modes()
            return result
        chains = {chain_id(c): c for c in self.session.chains}
        updates = {str(value(s, "chain_id")): s for s in suggestions}
        owned = {}
        for identity, chain in chains.items():
            entry = updates.get(identity, chain)
            for side in ("source", "target"):
                allowed = {node_id(n) for n in getattr(self.session, side)}
                ids = list(value(entry, side, []))
                if len(set(ids)) != len(ids) or any(str(i) not in allowed for i in ids):
                    raise ValueError("候选包含重复或失效节点，请手动重绑定。")
                if side == "target":
                    for node in ids:
                        if node in owned:
                            raise ValueError("目标节点被多条链使用：" + self.name("target", node))
                        owned[node] = identity
        old = {identity: (list(value(c, "source", [])), list(value(c, "target", []))) for identity, c in chains.items()}
        try:
            for identity, entry in updates.items():
                if identity not in chains:
                    raise ValueError("候选对应的关键链已经失效。")
                self.session.assign(identity, "source", list(value(entry, "source", [])))
                self.session.assign(identity, "target", list(value(entry, "target", [])))
        except Exception:
            for identity, (source, target) in old.items():
                chain = chains[identity]
                if isinstance(chain, dict):
                    chain.update(source=source, target=target)
                else:
                    chain.source, chain.target = source, target
            raise
        remember_confirmed_modes()

    def suggest(self):
        try:
            suggestions = self.session.suggestions()
            if not suggestions:
                self.notify("没有可用候选。可搜索节点后手工配置整链。")
                return
            dialog = SuggestionDialog(suggestions, self.session.chains, self.name, self)
            if dialog_exec(dialog) == QtWidgets.QDialog.Accepted:
                chosen = dialog.chosen()
                if chosen:
                    self.run(f"已应用 {len(chosen)} 条确认建议。", lambda: self._apply_mapping_batch(chosen), changed=True)
        except Exception as error:
            self.notify("自动匹配失败：" + str(error), error=True)

    def mirror_suggestion(self):
        from .matching import mirror_name
        chain = self.current_chain()
        if not chain:
            return
        label = value(chain, "label", chain_id(chain))
        mirrored_label = mirror_name(label)
        if mirrored_label == label:
            self.notify("当前链名没有可识别的左右标记。请先选择左臂、右腿等链。", error=True)
            return
        counterpart = next((c for c in self.session.chains if value(c, "label", chain_id(c)) == mirrored_label), None)
        row = {"chain_id": chain_id(counterpart) if counterpart else mirrored_label,
               "confidence": 0.9, "reason": "左右名称一一对应；仅镜像映射建议，未改变场景姿态"}
        for side in ("source", "target"):
            mapped = value(chain, side, [])
            if not mapped:
                self.notify("当前链尚未完成两侧映射，请先配置后再生成对侧候选。", error=True)
                return
            nodes = getattr(self.session, side)
            row[side] = []
            for identity in mapped:
                original = self.name(side, identity)
                mirrored = mirror_name(original)
                matches = [node_id(n) for n in nodes if value(n, "name", "") == mirrored]
                if mirrored == original or len(matches) != 1:
                    self.notify(f"{original} 的对侧节点缺失或重名，请手动配置。", error=True)
                    return
                row[side].append(matches[0])
        dialog = SuggestionDialog([row], self.session.chains, self.name, self)
        if dialog_exec(dialog) == QtWidgets.QDialog.Accepted and dialog.chosen():
            self.run("已应用确认的对侧链候选。", lambda: self._apply_mapping_batch(dialog.chosen()), changed=True)

    def preview(self):
        try:
            frame = float(self.session.host.current_frame())
        except Exception as error:
            self.notify("无法读取当前宿主时间：" + str(error), error=True)
            return
        def action():
            self.invalidate_preview()
            result = self.session.preview(frame, self.settings())
            self._preview_valid = True
            return result
        result = self.run(f"预览有效 · 帧 {frame:g}；配置改变或关闭窗口将恢复预览前状态。", action)
        if result is not None:
            self.log(str(result))

    def restore_preview(self):
        def action():
            result = self.session.restore_preview()
            self._preview_valid = False
            return result
        missing = self.run("已恢复预览前的目标数据。", action)
        if missing:
            self.notify(f"已恢复仍有效节点的预览前数据；{len(missing)} 个节点已失效，无法恢复。")

    def restore_last_bake(self):
        missing = self.run("已恢复上次烘焙之前的目标数据。", self.session.restore_last_bake, changed=True)
        if missing:
            self.notify(f"已恢复仍有效节点的烘焙前数据；{len(missing)} 个节点已失效，无法恢复。")

    @contextmanager
    def busy(self):
        self._busy = True
        self._cancel = False
        self.content.setEnabled(False)
        try:
            yield
        finally:
            self.content.setEnabled(True)
            self._busy = False

    def bake(self):
        if self._busy:
            return
        start, end, step = self.start.value(), self.end.value(), self.step.value()
        if end < start:
            self.notify("结束帧必须大于或等于开始帧。", error=True)
            return
        progress = QtWidgets.QProgressDialog("先完整采样源动画，再写入目标…", "取消并恢复", 0, 100, self)
        progress.setWindowTitle("烘焙重定向动画")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(lambda: setattr(self, "_cancel", True))
        def update(*args):
            # Session may report (done, total, label), (fraction, label), or
            # (percentage,). Qt event pumping keeps Cancel responsive without
            # moving any pymxs operation onto a worker thread.
            if not args:
                return
            done = float(args[0])
            if len(args) > 1 and isinstance(args[1], (int, float)):
                percent = int(100 * done / max(float(args[1]), 1))
                label = str(args[2]) if len(args) > 2 else ""
            else:
                percent = int(done * 100) if 0 <= done <= 1 else int(done)
                label = str(args[1]) if len(args) > 1 else ""
            progress.setValue(min(100, max(0, percent)))
            if label:
                progress.setLabelText(label)
            QtWidgets.QApplication.processEvents()
        last_poll = [0.0]
        def cancel_requested():
            now=time.monotonic()
            if now-last_poll[0]>=0.04:
                QtWidgets.QApplication.processEvents()
                last_poll[0]=now
            return self._cancel or progress.wasCanceled()
        try:
            self.invalidate_preview()
            with self.busy():
                progress.show()
                result = self.session.bake(start, end, step, self.settings(), progress=update,
                                           cancelled=cancel_requested)
            if self._cancel or progress.wasCanceled():
                self.notify("烘焙已取消；请查看会话恢复结果。")
            else:
                self.notify(f"烘焙成功 · 帧 {start}–{end} · 步长 {step}")
                if result is not None:
                    self.log(str(result))
            self.refresh()
        except CancelledError as error:
            self.notify("烘焙已取消；" + str(error))
        except Exception as error:
            self.notify("烘焙未完成：" + str(error), error=True)
        finally:
            progress.close()
            progress.deleteLater()

    def save_preset(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存重定向预设", "重定向预设.json", "JSON 预设 (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        def action():
            # Keep settings in the session for the versioned preset writer.
            self.sync_settings()
            return self.session.save_preset(path)
        self.run("已保存映射、参考姿态与设置预设。", action, changed=True)

    def load_preset(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "加载重定向预设", "", "JSON 预设 (*.json)")
        if not path:
            return
        def action():
            result = self.session.load_preset(path)
            settings = getattr(self.session, "settings", {})
            if isinstance(settings, dict):
                self._load_settings(settings)
            self.source_ref.setText("源参考来自预设")
            self.target_ref.setText("目标参考来自预设")
            self.reference_info.setText("已载入预设参考姿态。请核对骨架身份；重新绑定后应重新记录两侧参考姿态，再预检。")
            self._set_unresolved(value(result, "unresolved", []))
            self.tabs.setCurrentIndex(2)
            return result
        result = self.run("已读取预设；请检查待重绑定节点和参考姿态，再预检。", action, changed=True)
        if result is not None and self._unresolved:
            self.rebind_presets()

    def _set_unresolved(self, unresolved):
        self._unresolved = list(unresolved)
        self.rebind_button.setEnabled(bool(self._unresolved))
        self.rebind_button.setText(f"处理待重绑定（{len(self._unresolved)}）" if self._unresolved else "处理待重绑定")
        if self._unresolved:
            self.log(f"待重绑定 {len(self._unresolved)} 个节点：")
            for issue in self._unresolved:
                side = "源" if value(issue, "side", "source") == "source" else "目标"
                self.log(f"  {side} · {value(issue, 'name', '')} · {value(issue, 'reason', '')}")
        else:
            self.log("没有待重绑定节点。")

    def rebind_presets(self):
        if not self._unresolved:
            return
        dialog = RebindDialog(self.session, self._unresolved, self)
        if dialog_exec(dialog) != QtWidgets.QDialog.Accepted:
            return
        source, target = dialog.bindings()
        if not source and not target:
            return
        def action():
            result = self.session.apply_bindings(source, target)
            # Facade returns the remaining unresolved identities. Do not infer
            # success from the names or silently clear unresolved entries.
            unresolved = value(result, "unresolved", None)
            if unresolved is None:
                unresolved = [issue for issue in self._unresolved
                              if str(value(issue, "preset_id", "")) not in
                              (source if value(issue, "side", "source") == "source" else target)]
            self._set_unresolved(unresolved)
            return result
        self.run("已应用明确绑定；请检查参考姿态并重新预检。", action, changed=True)

    def _load_settings(self, settings):
        for combo, key in ((self.root_mode, "root_mode"), (self.scale_mode, "scale_mode"), (self.output_mode, "output_mode")):
            index = combo.findData(settings.get(key))
            if index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
        self.scale.blockSignals(True)
        self.scale.setValue(settings.get("scale", 1))
        self.scale.blockSignals(False)
        self.scale.setEnabled(self.scale_mode.currentData() == "manual")
        for spin, key in ((self.start, "start"), (self.end, "end"), (self.step, "step"),
                          (self.reference_frame, "reference_frame")):
            if key in settings:
                spin.blockSignals(True)
                spin.setValue(settings[key])
                spin.blockSignals(False)
        self._overrides = dict(settings.get("chain_overrides", {}))

    def closeEvent(self, event):
        if self._busy:
            self._cancel = True
            self.status.setText("正在取消并恢复本次烘焙；恢复完成后可关闭窗口。")
            event.ignore()
            return
        try:
            self.session.restore_preview()
            self._preview_valid = False
            self.session.restore_visibility()
        except Exception as error:
            self.notify("关闭前恢复失败，请保持窗口并检查：" + str(error), error=True)
            event.ignore()
            return
        event.accept()


_window = None


def show(session=None, parent=None):
    """Explicit user launch only; importing UI never opens the host window."""
    global _window
    if _window is not None:
        try:
            _window.show()
            return _window
        except RuntimeError:
            _window = None
    if session is None:
        from .host import MaxHost
        from .session import Session
        session = Session(MaxHost())
    if parent is None:
        try:
            import qtmax
            parent = qtmax.GetQMaxMainWindow()
        except ImportError:
            pass
    _window = RetargetWindow(session, parent)
    _window.destroyed.connect(lambda *_: _clear_window())
    _window.show()
    return _window


def _clear_window():
    global _window
    _window = None
