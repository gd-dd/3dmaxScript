import copy
import math
import unittest
from rig.rig_scale import display_size,measure,skeleton_scales


def bone(key,parent=None,start=(0,0,0),end=(0,0,10),**extra):
    return dict(id=key,parent=parent,category='bones',position=start,end=end,**extra)


def control(key,parent=None,**extra):
    return dict(id=key,parent=parent,category='controls',position=(1e9,1e9,1e9),**extra)


class RigScaleTests(unittest.TestCase):
    def test_two_rigs_share_world_root_without_merging(self):
        records=[control('world'),bone('a','world'),bone('a2','a',(0,0,10),(0,0,100)),
                 bone('b','world',(1000,0,0),(1000,0,2)),bone('b2','b',(1000,0,2),(1000,0,5)),
                 control('far','a'),dict(id='mesh',parent='a',category='models',position=(0,0,1e12))]
        before=copy.deepcopy(records);scales=skeleton_scales(records)
        self.assertEqual(scales['a']['height'],100);self.assertEqual(scales['b']['height'],5)
        self.assertNotEqual(scales['a']['group'],scales['b']['group']);self.assertNotIn('world',scales)
        self.assertEqual(scales['far']['height'],100);self.assertNotIn('mesh',scales);self.assertEqual(records,before)

    def test_interposed_controls_preserve_bone_component(self):
        s=skeleton_scales([bone('a'),control('c','a'),bone('b','c',(0,0,10),(0,0,20))])
        self.assertEqual(s['a']['height'],20);self.assertEqual(s['c']['group'],s['b']['group'])

    def test_tagged_disconnected_chains_and_goal(self):
        s=skeleton_scales([bone('pelvis',rigId='R'),bone('spine',start=(0,0,10),end=(0,0,50),rigId='R'),control('goal',rigId='R')])
        self.assertEqual(s['goal']['height'],50);self.assertEqual(s['pelvis']['group'],s['spine']['group'])

    def test_cloned_rig_ids_with_distinct_body_centers_stay_separate(self):
        s=skeleton_scales([control('c1',role='BodyCenter'),control('c2',role='BodyCenter'),
                          bone('a','c1',rigId='same'),bone('b','c2',end=(0,0,100),rigId='same'),
                          control('unanchored',rigId='same')])
        self.assertNotEqual(s['a']['group'],s['b']['group']);self.assertNotIn('unanchored',s)

    def test_partially_tagged_chain_inherits_ancestor_identity_under_body_center(self):
        records=[control('center',role='BodyCenter'),bone('a','center',rigId='R'),
                 control('between','a'),bone('b','between',(0,0,10),(0,0,100)),
                 control('goal',anchor='b')]
        s=skeleton_scales(records,targets=['b'])
        self.assertEqual(s['a']['height'],100);self.assertEqual(s['b']['group'],('rig','R','center'))
        self.assertEqual(s['goal']['group'],s['a']['group']);self.assertEqual(s['center']['height'],100)

    def test_child_only_tag_does_not_split_connected_untagged_ancestor(self):
        s=skeleton_scales([control('center',role='BodyCenter'),bone('a','center'),
                          bone('b','a',(0,0,10),(0,0,100),rigId='R')])
        self.assertEqual(s['a']['group'],s['b']['group']);self.assertEqual(s['a']['height'],100)

    def test_conflicting_connected_rig_tags_raise_without_merging(self):
        with self.assertRaises(ValueError):
            skeleton_scales([bone('a',rigId='R'),bone('b','a',rigId='different')])

    def test_nested_body_center_keeps_fully_tagged_rigs_independent(self):
        s=skeleton_scales([control('center_a',role='BodyCenter'),bone('a','center_a',rigId='A'),
                          control('center_b','a',role='BodyCenter'),bone('b','center_b',end=(0,0,100),rigId='B')])
        self.assertNotEqual(s['a']['group'],s['b']['group'])
        self.assertEqual(s['a']['height'],10);self.assertEqual(s['b']['height'],100)
        self.assertEqual(s['center_a']['group'],s['a']['group'])
        self.assertEqual(s['center_b']['group'],s['b']['group'])

    def test_biped_com_groups_undefined_controller_limbs_without_measuring_helpers(self):
        s=skeleton_scales([control('com',biped=True,controller='Vertical_Horizontal_Turn'),
                          control('steps','com',biped=True,controller='Footsteps'),
                          bone('pelvis','com',biped=True),bone('spine','pelvis',start=(0,0,10),end=(0,0,60),biped=True),
                          bone('finger','spine',start=(0,0,30),end=(0,0,31),biped=True,controller=None)])
        self.assertEqual(s['com']['height'],60);self.assertEqual(s['steps']['height'],60)
        self.assertEqual(s['finger']['group'],('biped','com'))

    def test_unparented_ik_anchor_and_cross_rig_rejection(self):
        records=[bone('a'),bone('b',end=(0,0,100)),control('ik',anchor='a',endJoint='a')]
        self.assertEqual(skeleton_scales(records)['ik']['height'],10)
        records[-1]['endJoint']='b'
        with self.assertRaises(ValueError):skeleton_scales(records)

    def test_targets_measure_whole_selected_rig_and_skip_degenerate_other_rig(self):
        records=[bone('a'),bone('a2','a',(0,0,10),(0,0,100)),control('goal',anchor='a'),
                 bone('far',start=(10000,0,0),end=(10000,0,0))]
        result=skeleton_scales(records,targets=['goal'])
        self.assertEqual(result['a']['height'],100);self.assertIn('a2',result);self.assertNotIn('far',result)
        with self.assertRaises(ValueError):skeleton_scales(records)
        with self.assertRaises(ValueError):skeleton_scales(records,targets=['missing'])
        self.assertEqual(skeleton_scales(records,targets=[]),{})

    def test_saved_control_group_maps_external_ik_circle_and_root(self):
        records=[bone('a'),bone('b',end=(0,0,100)),
                 control('root',controlGroup=['tree','a']),
                 control('circle','root',controlGroup=('tree','a')),
                 control('stale',controlGroup=['tree','missing']),
                 control('malformed',controlGroup=[['tree'],'a'])]
        result=skeleton_scales(records,targets=['circle'])
        self.assertEqual(result['circle']['height'],10);self.assertIn('root',result)
        self.assertNotIn('b',result);self.assertNotIn('stale',result);self.assertNotIn('malformed',result)
        records.append(control('conflict',controlGroup=['tree','a'],anchor='b'))
        with self.assertRaises(ValueError):skeleton_scales(records)

    def test_flat_skeleton_does_not_use_tiny_vertical_span(self):
        result=measure([bone('a',start=(0,0,0),end=(50,0,.01)),bone('b','a',(50,0,.01),(100,0,.02))])
        self.assertEqual(result['height'],100);self.assertEqual(result['method'],'largest_axis')

    def test_upright_height_ignores_wider_arms_and_translation(self):
        result=measure([bone('spine',start=(100,200,300),end=(100,200,470)),
                        bone('arm',start=(10,200,440),end=(210,200,440))])
        self.assertEqual(result['height'],170);self.assertEqual(result['method'],'world_z')

    def test_single_diagonal_bone_uses_segment_length(self):
        result=measure([bone('a',end=(3,4,0))])
        self.assertEqual(result['height'],5);self.assertEqual(result['method'],'segment_length')

    def test_uniform_scale_scales_display_without_fixed_floor(self):
        for factor in (1e-7,.01,1,10000):
            height=measure([bone('a',end=(0,0,170*factor))])['height']
            self.assertAlmostEqual(display_size(height,.04)/factor,6.8)

    def test_degenerate_nonfinite_empty_and_cyclic_inputs(self):
        for records in ([],[bone('a',end=(0,0,0))],[bone('a',end=(math.nan,0,1))],
                        [bone('a',end=(1.2e308,1.2e308,1.2e308))]):
            with self.assertRaises(ValueError):measure(records)
        with self.assertRaises(ValueError):skeleton_scales([bone('a','b'),bone('b','a')])
        with self.assertRaises(ValueError):skeleton_scales([bone('a'),bone('a')])
        for height,ratio in [(0,.04),(170,0),(math.inf,.04),(170,math.nan)]:
            with self.assertRaises(ValueError):display_size(height,ratio)


if __name__=='__main__':unittest.main()
