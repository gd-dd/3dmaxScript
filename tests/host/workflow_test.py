"""Read-only visual acceptance for the current Max workflow panel."""
import importlib,json
from pathlib import Path
from rig import theme,max_ui,brush,max_host as H
from PySide6.QtCore import QTimer
ROOT=Path(__file__).resolve().parents[2]
brush.stop();importlib.reload(theme)
dock=max_ui._dock
if dock is not None and not dock.closed:
 dock.widget().setStyleSheet(theme.STYLE);theme.apply_popup_palette(dock.widget())
 w=dock.workbench;w.load_scene(H.inspect_scene({}));w.steps.setCurrentIndex(6);w.load_skin(H.inspect_skin(w.params()))
 def capture():
  dock.grab().save(str(ROOT/'tests/workflow-weight-preview.png'));w.scope.showPopup()
  def popup():
   w.scope.view().grab().save(str(ROOT/'tests/workflow-scope-preview.png'));w.scope.hidePopup()
   (ROOT/'tests/host/ui-acceptance-report.json').write_text(json.dumps({'ok':True,'scope':w.scope.currentText(),'whiteBase':w.scope.view().palette().base().color().name()}),'utf-8')
  QTimer.singleShot(200,popup)
 QTimer.singleShot(500,capture)
