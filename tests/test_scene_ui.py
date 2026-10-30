import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from rig.workflow_ui import WorkflowWorkbench
from rig.scene_ui import role_label

class Owner:
    def rig_command(self,request,callback):raise AssertionError('Changing steps must not require another Max read')

def node(identity,name,category,role='',parent=None,skins=None):
    return dict(id=identity,name=name,workflow=category,role=role,parent=parent,geometry=category=='models',
                bone=category in ('bones','controls'),hidden=False,selected=False,skins=skins or [],
                **{'class':'BoneGeometry' if category=='bones' else 'Editable_Poly' if category=='models' else 'Point'})

class SharedSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=WorkflowWorkbench(Owner());self.w.set_target('scene')
        self.data={'scene':'scene','nodes':[node('center','BodyCenter','controls','BodyCenter'),node('hip','Pelvis','bones','Pelvis','center'),
            node('mesh1','BodyA','models'),node('mesh2','BodyB','models',skins=[{'name':'Skin A','index':0,'handle':'skinA'},{'name':'Skin B','index':1,'handle':'skinB'}])]}
        self.w.load_scene(self.data)
    def tearDown(self):self.w.deleteLater();self.app.processEvents()
    def test_context_survives_all_steps_and_scene_refresh(self):
        self.w.mesh.setCurrentIndex(self.w.mesh.findData('mesh2'));self.w.skin.setCurrentIndex(1)
        for i in range(self.w.steps.count()):
            self.w.steps.setCurrentIndex(i)
            self.assertEqual(self.w.mesh.currentData(),'mesh2');self.assertEqual(self.w.skin.currentData(Qt.ItemDataRole.UserRole+1),'skinB')
        self.w.load_scene(self.data);self.assertEqual(self.w.skin.currentData(Qt.ItemDataRole.UserRole+1),'skinB')
    def test_readable_hierarchy_and_search_keep_ancestors(self):
        center=self.w.tree.topLevelItem(0);self.assertEqual(center.child(0).text(1),'骨盆 / 摆胯')
        self.w.scene_search.setText('骨盆');self.assertFalse(center.isHidden());self.assertFalse(center.child(0).isHidden());self.assertTrue(self.w.tree.topLevelItem(1).isHidden())
    def test_center_is_not_accidentally_bound_as_bone(self):
        self.w.tree.topLevelItem(0).setSelected(True);self.assertEqual(self.w.selected_bones(),[])
        self.w.tree.topLevelItem(0).child(0).setSelected(True);self.assertEqual(self.w.selected_bones(),['hip'])
    def test_role_labels_distinguish_sides_and_chain_links(self):
        self.assertEqual(role_label({'role':'L_UpperArm_02'}),'左 · 上臂 · 02')
        self.assertEqual(role_label({'role':'R_Clavicle'}),'右 · 肩 / 锁骨')

if __name__=='__main__':unittest.main()
