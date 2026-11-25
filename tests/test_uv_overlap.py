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
