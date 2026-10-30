import unittest,math,random
from rig import weights as w

class WeightsTests(unittest.TestCase):
    def test_locked_edit(self):
        r=w.edit({'1':.2,'2':.3,'3':.5},'2',.6,locked=['1'])
        self.assertAlmostEqual(r['1'],.2);self.assertAlmostEqual(r['3'],.2);self.assertAlmostEqual(sum(r.values()),1)
        with self.assertRaises(ValueError):w.edit(r,'1',.3,locked=['1'])
        with self.assertRaises(ValueError):w.edit(r,'2',.9,locked=['1'])
    def test_reject_invalid(self):
        for v in (float('inf'),float('nan'),-1):
            with self.assertRaises(ValueError):w.normalize({'1':v})
        with self.assertRaises(ValueError):w.normalize({})
        with self.assertRaises(ValueError):w.normalize({'1':.8,'2':.5},['1','2'])
    def test_prune_preserves_locks(self):
        r=w.prune({'1':.01,'2':.49,'3':.5},.1,2,['1'])
        self.assertEqual(set(r),{'1','3'});self.assertAlmostEqual(r['1'],.01)
    def test_tiny_locked_weight_is_not_dropped(self):
        r=w.prune({'1':1e-9,'2':1-1e-9},.001,2,['1'])
        self.assertEqual(r['1'],1e-9)
    def test_smoothing_boundary_and_lock(self):
        rows=[{'1':.2,'2':.8},{'1':1},{'2':1}]
        out=w.smooth(rows,w.adjacency(3,[[0,1,2]]),[0],.5,2,['1'])
        self.assertEqual(out[1:],rows[1:]);self.assertAlmostEqual(out[0]['1'],.2);self.assertEqual(rows[0],{'1':.2,'2':.8})
    def test_mirror_and_rejection(self):
        rows=[{'1':1},{'1':.25,'2':.75}];points=[[-1,0,0],[1,0,0]]
        out=w.mirrored(rows,points,{'1':'2','2':'1'},[0,1])
        self.assertEqual(out[0],{'2':.25,'1':.75});self.assertEqual(out[1],rows[1])
        with self.assertRaises(ValueError):w.mirrored(rows,[[-2,0,0],[1,0,0]],{},[0,1])
    def test_kdtree_matches_bruteforce(self):
        random.seed(3);points=[[random.random() for _ in range(3)] for _ in range(60)];index=w.PointIndex(points)
        for _ in range(20):
            p=[random.random() for _ in range(3)];expected=min(range(len(points)),key=lambda i:(sum((a-b)**2 for a,b in zip(points[i],p)),i))
            self.assertEqual(index.nearest(p)[0],expected)
    def test_transfer_distance(self):
        self.assertEqual(w.transfer([{'1':1}],[[0,0,0]],[[.1,0,0]],1),[{'1':1}])
        with self.assertRaises(ValueError):w.transfer([{'1':1}],[[0,0,0]],[[2,0,0]],1)
    def test_diagnostics(self):
        self.assertEqual(len(w.validate_rows([{}, {'5':1},{'1':.2}],['1'])),3)
        self.assertEqual(w.validate_rows([{'1':1}],['1']),[])

if __name__=='__main__':unittest.main()
