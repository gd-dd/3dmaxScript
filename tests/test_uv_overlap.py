import unittest

from uv_overlap import Alignment, islands


class UVOverlapTests(unittest.TestCase):
    def test_matching_grid_uses_exact_correspondence(self):
        a = [(1,2,5),(2,3,5),(3,4,5),(4,1,5)]
        b = [tuple(i+5 for i in face) for face in a]
        points = dict(enumerate([0j,3+0j,3+1j,1j,1+.3j],1))
        points.update({i+5:2j*p+4 for i,p in list(points.items())})
        plan = Alignment(points,a,b)
        result, mode = plan.result(0)
        self.assertEqual(mode,'逐点重叠')
        self.assertEqual(result,{i+5:p for i,p in points.items() if i<=5})
        self.assertNotEqual(plan.result(1)[0],result)
        detected = islands(dict(enumerate(a+b,1)),[2,5])
        self.assertEqual([set(group) for group in detected],[set(a),set(b)])

    def test_extra_edge_points_are_interpolated_between_corners(self):
        points = dict(enumerate([0j,3+0j,3+1j,1j,4j,1+4j,3+4j,3+5j,5j],1))
        plan = Alignment(points,[(1,2,3,4)],[(5,6,7,8,9)])
        result, mode = plan.result(0)
        self.assertIn('转角',mode)
        self.assertTrue(all(any(abs(p-result[j])<1e-9 for j in (5,7,8,9)) for p in (0j,3+0j,3+1j,1j)))
        self.assertTrue(any(abs(result[6]-p)<1e-9 for p in (1+0j,2+1j)))

    def test_requires_closed_continuous_boundary(self):
        with self.assertRaisesRegex(ValueError,'连续'):
            Alignment({},[(1,2,3),(1,4,5)],[(6,7,8)])


    def ring_grid(self, a_holes, b_holes):
        a, b = [], []
        points = {1+y*6+x:complex(x,y) for y in range(5) for x in range(6)}
        points.update({i+30:7+2j*p for i,p in list(points.items())})
        for faces,holes,offset in ((a,a_holes,0),(b,b_holes,30)):
            for y in range(4):
                for x in range(5):
                    if (x,y) not in holes:
                        i = 1+y*6+x+offset
                        faces.append((i,i+1,i+7,i+6))
        return points,a,b

    def test_two_holes_auto_pair_and_allow_manual_override(self):
        holes = {(1,1),(3,2)}
        points,a,b = self.ring_grid(holes,holes)
        plan = Alignment(points,a,b)
        result,mode = plan.result(0)
        self.assertEqual(plan.matched,{0:0,1:1,2:2})
        self.assertEqual(mode,'逐点重叠')
        self.assertEqual(result,{i:points[i-30] for i in plan.nb})
        result,_ = plan.result(0,{1:2})
        self.assertEqual(plan.matched,{0:0,1:2,2:1})
        self.assertEqual({result[i] for i in plan.contours_b[2]},{points[i] for i in plan.contours_a[1]})
        plan.result(0,{1:None})
        self.assertEqual(plan.matched,{0:0,2:2})

    def test_unequal_hole_counts_keep_unmatched_boundaries(self):
        points,a,b = self.ring_grid({(1,1)},{(1,1),(3,2)})
        plan = Alignment(points,a,b)
        result,_ = plan.result(0)
        self.assertEqual(plan.matched,{0:0,1:1})
        self.assertEqual(set(result),set(plan.nb))
        for i in plan.contours_b[2]:
            self.assertAlmostEqual(abs(result[i]-points[i-30]),0.)


    def test_different_hole_point_counts_follow_matching_corners(self):
        points,a,b = self.ring_grid({(1,1)},{(1,1)})
        original = Alignment(points,a,b)
        left,right = original.contours_b[1][:2]
        mid = max(points)+1
        points[mid] = (points[left]+points[right])/2
        for i,face in enumerate(b):
            for j,vertex in enumerate(face):
                if {vertex,face[(j+1)%len(face)]} == {left,right}:
                    b[i] = face[:j+1]+(mid,)+face[j+1:]
                    break
        plan = Alignment(points,a,b)
        result,_ = plan.result(0)
        self.assertEqual(plan.matched,{0:0,1:1})
        self.assertEqual(len(plan.contours_b[1]),5)
        self.assertAlmostEqual(abs(result[mid]-(points[left-30]+points[right-30])/2),0.)


    def test_symmetry_is_flagged_and_one_anchor_sets_exact_phase(self):
        square = [0j, 2+0j, 2+2j, 2j]
        points = dict(enumerate(square + [point+5 for point in square], 1))
        plan = Alignment(points,[(1,2,3,4)],[(5,6,7,8)])
        self.assertTrue(plan.ambiguous)
        pairs = [(2,0),(3,1)]
        plan.validate_edge_pairs(pairs)
        result,mode = plan.result(0,edge_pairs=pairs)
        self.assertEqual(mode,'逐点重叠')
        self.assertEqual(result,{5:points[3],6:points[4],7:points[1],8:points[2]})
        self.assertEqual(result,plan.result(1,edge_pairs=pairs)[0])

    def test_distinct_outline_has_an_unambiguous_auto_match(self):
        outline = [0j,4+0j,3+2j,1+3j,2j]
        points = dict(enumerate(outline + [5-2j*value for value in outline], 1))
        plan = Alignment(points,[(1,2,3,4,5)],[(6,7,8,9,10)])
        self.assertFalse(plan.ambiguous)
        self.assertEqual(plan.result(0)[0],{i:points[i-5] for i in range(6,11)})
        with self.assertRaisesRegex(ValueError,'相位'):
            plan.validate_edge_pairs([(0,0),(2,3)])

    def test_unequal_outlines_honor_manual_endpoints_and_interpolate(self):
        points = dict(enumerate([0j,3+0j,3+1j,1j,4j,1+4j,3+4j,3+5j,5j],1))
        plan = Alignment(points,[(1,2,3,4)],[(5,6,7,8,9)])
        pairs = [(1,2),(3,4)]
        result,_ = plan.result(0,edge_pairs=pairs)
        self.assertEqual([result[i] for i in (5,7,8,9)],[points[i] for i in (1,2,3,4)])
        self.assertAlmostEqual(abs(result[6]-1),0)
        with self.assertRaisesRegex(ValueError,'共用端点'):
            plan.validate_edge_pairs([(0,0),(2,1)])

    def test_reverse_direction_swaps_manually_selected_edge_endpoints(self):
        outline = [0j,4+0j,3+2j,1+3j,2j]
        points = dict(enumerate(outline + [value+8 for value in outline],1))
        plan = Alignment(points,[(1,2,3,4,5)],[(6,7,8,9,10)])
        pairs = [(1,0)]
        normal,_ = plan.result(0,edge_pairs=pairs)
        flipped,_ = plan.result(0,edge_pairs=pairs,flip_pairs=True)
        self.assertEqual((normal[6],normal[7]),(points[2],points[3]))
        self.assertEqual((flipped[6],flipped[7]),(points[3],points[2]))


    def test_unequal_outlines_reject_crossing_manual_pairs(self):
        outer = [0j,2+0j,3+1j,2+3j,1+3j,1j]
        moving = [value+6 for value in outer]+[5+2j,5+1j]
        points = dict(enumerate(outer+moving,1))
        plan = Alignment(points,[(1,2,3,4,5,6)],[tuple(range(7,15))])
        with self.assertRaisesRegex(ValueError,'顺序交叉'):
            plan.validate_edge_pairs([(0,0),(4,2),(2,4)])


    def test_all_contours_can_be_repaired_with_the_same_edge_solver(self):
        points,a,b = self.ring_grid({(1,1)},{(1,1)})
        plan = Alignment(points,a,b)
        plan.result(0,{0:1,1:0})
        self.assertEqual(plan.matched,{0:1,1:0})
        self.assertEqual(plan.unmatched_a,())
        self.assertEqual(plan.unmatched_b,())
        plan.validate_contour_edges(0,1,[(0,0)])
        plan.validate_contour_edges(1,0,[(0,0)])
        result,_ = plan.result(0,{0:1,1:0},contour_edges={
            (0,1): ([(0,0)],False), (1,0): ([(0,0)],False)})
        for a_index,b_index in plan.matched.items():
            profile = plan.contour_boundaries[a_index,b_index]
            target = profile.a[:2] if profile.direction>0 else profile.a[1::-1]
            self.assertEqual([result[i] for i in profile.b[:2]], [points[i] for i in target])

    def test_manual_edge_pins_and_phase_are_independent_by_contour(self):
        points,a,b = self.ring_grid({(1,1)},{(1,1)})
        plan = Alignment(points,a,b)
        initial,_ = plan.result()
        profile = plan.contour_boundaries[1,1]
        phase_result,_ = plan.result(contour_phases={(1,1):1})
        self.assertEqual([initial[i] for i in plan.contours_b[0]],
                         [phase_result[i] for i in plan.contours_b[0]])
        self.assertNotEqual([initial[i] for i in profile.b],[phase_result[i] for i in profile.b])
        anchor = (1,0)
        plan.validate_contour_edges(1,1,[anchor])
        edited,_ = plan.result(contour_edges={(1,1):([anchor],False)})
        a_edge = profile.a[1:3] if profile.direction>0 else profile.a[2:0:-1]
        self.assertEqual([edited[i] for i in profile.b[:2]], [points[i] for i in a_edge])
        self.assertEqual([initial[i] for i in plan.contours_b[0]],
                         [edited[i] for i in plan.contours_b[0]])

    def test_unmatched_contour_vertices_are_not_pinned_to_other_contours(self):
        points,a,b = self.ring_grid({(1,1)},{(1,1)})
        plan = Alignment(points,a,b)
        vertex = plan.contours_b[1][0]
        points[vertex] += .23
        plan = Alignment(points,a,b)
        result,_ = plan.result(overrides={1:None})
        self.assertEqual(plan.unmatched_a,(1,))
        self.assertEqual(plan.unmatched_b,(1,))
        boundaries_a = {points[i] for contour in plan.contours_a for i in contour}
        self.assertNotIn(result[vertex], boundaries_a)
        self.assertLess(abs(result[vertex]-points[vertex-30]),.2)

    def test_no_matching_contours_still_returns_free_positions(self):
        points = dict(enumerate([0j,5+0j,4+3j,2j,10j,6+10j,4+12j,12j],1))
        plan = Alignment(points,[(1,2,3,4)],[(5,6,7,8)])
        result,mode = plan.result(overrides={0:None})
        self.assertEqual(plan.matched,{})
        self.assertEqual(plan.unmatched_a,(0,))
        self.assertEqual(plan.unmatched_b,(0,))
        self.assertEqual(mode,'内部映射')
        self.assertEqual(result.keys(),plan.nb.keys())
        self.assertLess(len(set(result.values()) & set(points[i] for i in plan.a)),len(plan.a))
