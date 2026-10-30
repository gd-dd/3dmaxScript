"""LX palette: white, leaf green, restrained champagne focus."""
STYLE='''
QWidget { background-color:#FFFFFF; color:#202020; font-family:"Microsoft YaHei UI"; font-size:12px; }
QDockWidget { background:#FFFFFF; }
QLabel { background:transparent; }
QPushButton { background:#FFFFFF; border:1px solid rgba(119,119,119,65); border-radius:7px; padding:8px 10px; min-height:18px; }
QPushButton:hover { background:rgba(134,184,61,28); border-color:#86B83D; }
QPushButton:focus { border:2px solid #86B83D; background:#FFFAF0; }
QPushButton:checked { background:#507522; color:#FFFFFF; border-color:#507522; }
QPushButton:disabled { color:#777777; background:#FFFFFF; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#FFFFFF; border:1px solid rgba(119,119,119,75); border-radius:5px; padding:6px; selection-background-color:#86B83D; }
QComboBox:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled,QLineEdit:disabled {background:#FFFFFF;color:#777777;}
QComboBox#WorkflowSteps { color:#507522; font-size:16px; font-weight:600; min-height:32px; border:1px solid #86B83D; background:rgba(134,184,61,20); }
QComboBox QAbstractItemView { background:#FFFFFF; color:#202020; selection-background-color:#507522; selection-color:#FFFFFF; border:1px solid #86B83D; outline:0; }
QComboBox QAbstractItemView::item { min-height:28px; padding:4px 8px; }
QComboBox QAbstractItemView::item:selected { background:#507522; color:#FFFFFF; }
QTreeWidget { background:#FFFFFF; alternate-background-color:rgba(134,184,61,14); border:1px solid rgba(119,119,119,55); border-radius:6px; }
QTreeWidget::item { padding:5px; }
QTreeWidget::item:selected { color:#202020; background:rgba(134,184,61,65); }
QHeaderView::section { background:rgba(134,184,61,30); color:#507522; border:0; padding:6px; }
QTabWidget::pane { border:0; background:#FFFFFF; }
QTabBar::tab { padding:8px; background:#FFFFFF; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#507522; border-bottom-color:#86B83D; }
QScrollArea,QScrollArea>QWidget>QWidget { background:#FFFFFF; border:0; }
QScrollBar:vertical { background:transparent; width:9px; }
QScrollBar::handle:vertical { background:#86B83D; border-radius:4px; min-height:28px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QCheckBox { spacing:7px; padding:4px; }
'''


def apply_popup_palette(root):
    from PySide6.QtGui import QPalette,QColor
    from PySide6.QtWidgets import QComboBox
    for combo in root.findChildren(QComboBox):
        palette=combo.palette()
        for group in (QPalette.ColorGroup.Active,QPalette.ColorGroup.Inactive,QPalette.ColorGroup.Disabled):
            for role,color in ((QPalette.ColorRole.Button,'#FFFFFF'),(QPalette.ColorRole.Base,'#FFFFFF'),(QPalette.ColorRole.Window,'#FFFFFF'),(QPalette.ColorRole.Text,'#202020'),(QPalette.ColorRole.ButtonText,'#202020'),(QPalette.ColorRole.Highlight,'#507522'),(QPalette.ColorRole.HighlightedText,'#FFFFFF')):
                palette.setColor(group,role,QColor(color))
        combo.setPalette(palette);combo.view().setPalette(palette);combo.view().viewport().setPalette(palette);combo.view().viewport().setAutoFillBackground(True)
        combo.view().setStyleSheet('QAbstractItemView {background:#FFFFFF;color:#202020;selection-background-color:#507522;selection-color:#FFFFFF;border:1px solid #86B83D;} QAbstractItemView::item {min-height:28px;padding:4px 8px;} QAbstractItemView::item:selected {background:#507522;color:#FFFFFF;}')
