import math,unittest
from rig.bone_creation import segment


class BoneDirectionTests(unittest.TestCase):
    def test_direction_distance_never_changes_length(self):
        for distance in (.01,1,10000):
            a,b=segment((5,2,-1),(5,2+distance,-1),7)
            self.assertAlmostEqual(math.dist(a,b),7)
            self.assertEqual(b,(5,9,-1))
    def test_diagonal_direction(self):
        a,b=segment((1,2,3),(3,4,5),9)
        self.assertAlmostEqual(math.dist(a,b),9)
        self.assertAlmostEqual(b[0]-a[0],b[2]-a[2])
    def test_invalid_inputs_fail_before_host_use(self):
        for a,b,length in [((0,0,0),(0,0,0),1),((0,0,0),(1,0,0),0),((0,0,0),(1,0,0),float('nan')),((0,0),(1,0,0),1),((0,0,0),(float('inf'),0,0),1)]:
            with self.assertRaises(ValueError):segment(a,b,length)
        with self.assertRaises(ValueError):segment((-1e308,0,0),(1e308,0,0),1)
