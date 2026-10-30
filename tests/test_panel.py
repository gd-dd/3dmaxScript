import os,sys,unittest,json
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from ui.panel import MaxPanel
from rig.workbench import RigWorkbench
ROOT=Path(__file__).resolve().parents[1]
class Context:
    package_root=ROOT
    def resource(self,p):return ROOT/p
    def load_settings(self):return {}
    def save_settings(self,s):pass
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.panel=MaxPanel(Context())
    def tearDown(self):self.panel.shutdown();self.panel.deleteLater()
    def test_no_start_on_render(self):
        self.assertEqual(int(self.panel.process.state().value),0)
        self.assertFalse(hasattr(self.panel,'rig'))
        self.assertIn('rig-workbench',self.panel.buttons)
    def test_closed_selection_never_moves_to_other_window(self):
        self.panel.active_id='closed'
        self.panel.apply_response({'sessions':[{'id':'other','state':'ready','detail':'Other Max'}]})
        self.assertIsNone(self.panel.active_id)
        self.assertFalse(any(button.isEnabled() for button in self.panel.buttons.values()))
    def test_target_switch_discards_late_result(self):
        r=RigWorkbench(self.panel);r.set_target('one');callbacks=[]
        self.panel.rig_command=lambda req,cb:callbacks.append(cb)
        r.call('scene.inspect');r.set_target('two')
        callbacks[0]({'ok':True,'data':{'scene':'old','nodes':[]}})
        self.assertIsNone(r.scene);self.assertFalse(r.busy)
    def test_scene_and_controls(self):
        r=RigWorkbench(self.panel);r.set_target('test');r.load_scene({'scene':'abc','nodes':[{'id':'1','name':'Body','class':'Editable_mesh','parent':None,'geometry':True,'selected':True,'skins':[{'index':0,'name':'Skin'}]}]})
        self.assertEqual(r.mesh.currentData(),'1');self.assertEqual(r.skin.currentData(),0);self.assertTrue(r.body.isEnabled())
        self.assertEqual(r.scope.currentData(),'selected')
        r.load_skin({'profile':{'schema':1,'locked':['2'],'pairs':{},'humanoid':{},'face':{}},'count':9,'selectedCount':2,'vertex':1,'bones':[{'id':'2','name':'hip'}],'weights':{'2':1},'snapshots':[]})
        self.assertEqual(r.bone.currentData(),'2');self.assertEqual(r.locks.topLevelItemCount(),1)
        self.panel.resize(1000,1100);self.panel.show();self.app.processEvents();self.panel.grab().save(str(ROOT/'tests/panel-preview.png'))
if __name__=='__main__':unittest.main()
