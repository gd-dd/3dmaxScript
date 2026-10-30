import unittest
from rig import humanoid,binding,weight_edit,weights

def box(x=0):
 p=[[x+a,b,c] for a,b,c in [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]]
 f=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
 return p,f
class WorkflowAlgorithms(unittest.TestCase):
 def test_human_parent_complete(self):
  specs=humanoid.plan(dict(height=180,fingers=5,toes=5,upperArm=3,forearm=2));seen=set()
  for b in specs:
   self.assertTrue(b['parent'] is None or b['parent'] in seen);self.assertNotIn(b['role'],seen);seen.add(b['role'])
   self.assertGreater(binding.distance(b['start'],b['end']),0)
  self.assertIn('R_Toe4_02',seen);self.assertIn('L_UpperArm_03',seen)
 def test_segment_uses_length(self):
  rows,_=binding.solve([[9,.1,0]],[],[('a',[0,0,0],[10,0,0]),('b',[9,2,0],[9,3,0])],limit=1)
  self.assertEqual(rows,[{'a':1}])
 def test_voxel_disconnected_volumes_dont_cross(self):
  p,f=box();p2,f2=box(1.12);f+= [[i+8 for i in tri] for tri in f2];p+=p2
  rows,stats=binding.solve(p,f,[('a',[.3,.5,.5],[.7,.5,.5]),('b',[1.42,.5,.5],[1.82,.5,.5])],'voxel',4,2,24)
  self.assertTrue(stats['cells']>0);self.assertTrue(all(set(r)=={'a'} for r in rows[:8]));self.assertTrue(all(set(r)=={'b'} for r in rows[8:]))
 def test_open_mesh_rejected(self):
  p,f=box()
  with self.assertRaisesRegex(ValueError,'封闭'):binding.solve(p,f[:-1],[('a',[.5,.5,.2],[.5,.5,.8])],'voxel')
 def test_top_n_per_vertex(self):
  result=weights.prune({'1':.4,'2':.3,'3':.15,'4':.1,'5':.05},0,2)
  self.assertEqual(set(result),{'1','2'});self.assertAlmostEqual(sum(result.values()),1)
 def test_group_edit_preserves_ratio_and_locks(self):
  result=weight_edit.edit_many({'1':.2,'2':.1,'3':.5,'4':.2},['1','2'],.6,'set',['4'])
  self.assertAlmostEqual(result['1'],.4);self.assertAlmostEqual(result['2'],.2);self.assertAlmostEqual(result['4'],.2)
 def test_group_subtract_clamps(self):
  result=weight_edit.edit_many({'1':.2,'2':.8},['1'],.5,'subtract');self.assertEqual(result,{'2':1})
class PaletteTests(unittest.TestCase):
 def test_scope_popup_and_disabled_palette_are_white(self):
  import os
  os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
  from PySide6.QtWidgets import QApplication,QWidget,QComboBox
  from PySide6.QtGui import QPalette
  from rig.theme import apply_popup_palette
  app=QApplication.instance() or QApplication([]);root=QWidget();scope=QComboBox(root);scope.addItem('Selected')
  apply_popup_palette(root)
  for group in (QPalette.ColorGroup.Active,QPalette.ColorGroup.Inactive,QPalette.ColorGroup.Disabled):
   self.assertEqual(scope.view().palette().color(group,QPalette.ColorRole.Base).name(),'#ffffff')
   self.assertEqual(scope.view().palette().color(group,QPalette.ColorRole.Text).name(),'#202020')
   self.assertEqual(scope.view().palette().color(group,QPalette.ColorRole.HighlightedText).name(),'#ffffff')
class NumericWheelTests(unittest.TestCase):
 def test_wheel_never_changes_integer_or_decimal(self):
  import os
  os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
  from PySide6.QtWidgets import QApplication
  from PySide6.QtCore import QPoint,QPointF,Qt
  from PySide6.QtGui import QWheelEvent
  from rig.workbench import WheelSafeSpinBox,WheelSafeDoubleSpinBox
  app=QApplication.instance() or QApplication([])
  for cls in (WheelSafeSpinBox,WheelSafeDoubleSpinBox):
   field=cls();field.setValue(5)
   for delta in (120,-120):
    event=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(field,event);self.assertEqual(field.value(),5);self.assertFalse(event.isAccepted())
if __name__=='__main__':unittest.main()
