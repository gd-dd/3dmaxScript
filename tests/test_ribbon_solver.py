import sys, unittest, math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ribbon.solver import Solver,length,sub
class PhysicsTests(unittest.TestCase):
 def test_lengths_and_finite(self):
  s=Solver([(0,0,0),(10,0,0),(30,0,0)],mass=.01,influence=3)
  for i in range(1000):
   p=s.step((math.sin(i*.01)*5,0,0),1/240)
   self.assertAlmostEqual(length(sub(p[1],p[0])),10)
   self.assertAlmostEqual(length(sub(p[2],p[1])),20)
   self.assertTrue(all(math.isfinite(x) for v in p for x in v))
 def test_stationary(self):
  s=Solver([(0,0,0),(10,0,0)],gravity=0)
  for i in range(100): s.step((0,0,0),1/240)
  self.assertEqual(s.p,[(0,0,0),(10,0,0)])
 def test_mass_response(self):
  a=Solver([(0,0,0),(10,0,0)],mass=.1)
  b=Solver([(0,0,0),(10,0,0)],mass=10)
  for i in range(30): a.step((0,0,0),1/240); b.step((0,0,0),1/240)
  self.assertNotEqual(a.p,b.p)
if __name__=='__main__': unittest.main()
