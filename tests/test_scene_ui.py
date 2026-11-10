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
        self.w.category_trees['controls'].topLevelItem(0).setSelected(True);self.assertEqual(self.w.selected_bones(),[])
        self.w.category_trees['bones'].topLevelItem(0).setSelected(True);self.assertEqual(self.w.selected_bones(),['hip'])
    def test_model_and_bone_multiselection_are_independent(self):
        models=self.w.category_trees['models'];bones=self.w.category_trees['bones']
        models.topLevelItem(0).setSelected(True);models.topLevelItem(1).setSelected(True);bones.topLevelItem(0).setSelected(True)
        self.assertEqual(set(self.w.selected_models()),{'mesh1','mesh2'});self.assertEqual(self.w.selected_bones(),['hip'])
        self.w.load_scene(self.data)
        self.assertEqual(set(self.w.selected_models()),{'mesh1','mesh2'});self.assertEqual(self.w.selected_bones(),['hip'])
    def test_segment_bending_off_and_mixed_selection_present(self):
        self.assertFalse(self.w.bend_segments.isChecked());self.assertGreaterEqual(self.w.component.findData('mixed'),0)
        self.assertTrue(self.w.color_view.isChecked())
    def test_two_panes_keep_three_independent_selections_after_resizing(self):
        self.w.show()
        for tree in self.w.category_trees.values():tree.topLevelItem(0).setSelected(True)
        self.assertEqual(self.w.category_split.count(),2)
        for width,height in [(800,600),(1500,1400),(950,700)]*8:
            self.w.resize(width,height);self.app.processEvents()
        for index in (1,0,1,0):self.w.role_tabs.setCurrentIndex(index)
        self.assertEqual(self.w.selected_models(),['mesh1']);self.assertEqual(self.w.selected_bones(),['hip'])
        self.assertEqual(set(self.w.selected()),{'hip','center'})
        self.assertGreater(self.w.category_split.height(),150)
        self.w.close()
    def test_idle_preview_does_not_reread_weights_and_resize_defers_work(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock,patch
        view=SimpleNamespace(signature=lambda *args:tuple(map(str,args)),update=Mock(return_value=[]),clear=Mock())
        host=SimpleNamespace(rt=SimpleNamespace(theHold=SimpleNamespace(Holding=lambda:False)))
        self.w.show();self.app.processEvents()
        with patch.dict(sys.modules,{'rig.weight_view':view,'rig.max_host':host}),patch('rig.weight_view',view,create=True),patch('rig.max_host',host,create=True):
            self.w.invalidate_preview()
            self.w.refresh_weight_view()
            self.assertEqual(view.update.call_count,0)
            self.w.steps.setCurrentIndex(6)
            for _ in range(20):self.w.refresh_weight_view()
            self.assertEqual(view.update.call_count,1)
            self.w.owner._preview_resizing=True;self.w.invalidate_preview();self.w.refresh_weight_view()
            self.assertEqual(view.update.call_count,1)
            self.w.owner._preview_resizing=False;self.w.refresh_weight_view()
            self.assertEqual(view.update.call_count,2)
        self.w.close()
    def test_visibility_includes_unimported_listed_objects(self):
        from unittest.mock import Mock
        self.w.nodes[2]['workflow']=''
        self.w.call=Mock()
        button=Mock()
        self.w.visibility('models',False,button,'模型')
        args=self.w.call.call_args.args
        self.assertEqual(set(args[1]['nodes']),{'mesh1','mesh2'})
        args[2]({})
        self.assertTrue(self.w.nodes[2]['hidden'])
    def test_existing_biped_and_unmarked_models_are_visible_by_default(self):
        data={'scene':'scene','nodes':self.data['nodes']+[
            dict(node('bip','Bip001 Pelvis','','',None),category='bones',geometry=False,bone=True,**{'class':'Biped_Object'}),
            dict(node('com','Bip001','','',None),category='controls',geometry=False,bone=False,**{'class':'Biped_Object'}),
            dict(node('existing','Old Mesh','models'),workflow='')]}
        self.w.load_scene(data)
        self.assertFalse(self.w.workflow_only.isChecked())
        from rig.selection_ui import items
        for key,ref in [('models','existing'),('bones','bip'),('controls','com')]:
            item=next(i for i in items(self.w.category_trees[key]) if i.data(0,Qt.ItemDataRole.UserRole)==ref)
            self.assertFalse(item.isHidden())
        self.assertNotIn('bip',[self.w.mesh.itemData(i) for i in range(self.w.mesh.count())])
    def test_role_labels_distinguish_sides_and_chain_links(self):
        self.assertEqual(role_label({'role':'L_UpperArm_02'}),'左 · 上臂 · 02')
        self.assertEqual(role_label({'role':'R_Clavicle'}),'右 · 肩 / 锁骨')

    def test_child_parent_survives_reference_pick_and_extend_ignores_coordinates(self):
        from unittest.mock import Mock
        self.w.set_child_parent({'node':'hip','name':'Pelvis'})
        self.w.call=Mock();self.w.capture_child_point('direction','vertex')
        self.w.call.call_args.args[2]({'position':[30,40,50],'message':'vertices'})
        self.assertEqual(self.w.child_direction.text(),'30, 40, 50')
        self.assertEqual(self.w.child_parent,'hip')
        self.w.child_start.setText('invalid unused value');self.w.child_length.setValue(7)
        self.w.add_child(True)
        action,params,callback=self.w.call.call_args.args
        self.assertEqual(action,'bone.child');self.assertEqual(params['parent'],'hip')
        self.assertEqual(params['length'],7);self.assertTrue(params['extend'])
        self.assertNotIn('start',params);self.assertNotIn('direction',params)
        callback({'node':'child','name':'NewBone'})
        self.assertEqual(self.w.child_parent,'child')
        self.w.load_scene(dict(self.data,scene='another'))
        self.assertIsNone(self.w.child_parent);self.assertEqual(self.w.child_direction.text(),'')

    def test_deleted_child_parent_can_fall_back_then_refresh_clears_it(self):
        from unittest.mock import Mock
        self.w.set_child_parent({'node':'deleted','name':'UndoneBone'})
        self.w.choose_bone_nodes(['hip']);self.w.call=Mock();self.w.add_child(True)
        self.assertEqual(self.w.call.call_args.args[1]['fallbackParent'],'hip')
        self.w.load_scene(self.data);self.assertIsNone(self.w.child_parent)

if __name__=='__main__':unittest.main()
