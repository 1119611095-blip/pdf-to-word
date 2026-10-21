import math,unittest
from core import Settings,Curve,ESR,Demo

class CoreTest(unittest.TestCase):
    def test_frequency_coverage(self):
        s=Settings();s.validate();fs=s.frequencies()
        self.assertEqual(fs[0],150000);self.assertEqual(fs[-1],30000000)
        self.assertTrue(all(0<b-a<=4500 for a,b in zip(fs,fs[1:])))
        self.assertEqual(Settings(start=1e6,stop=1e6).frequencies(),[1e6])
    def test_bad_parameters(self):
        for params in ({'step':0},{'step':10000},{'start':float('nan')},{'stop':1},{'dwell':float('inf')},{'step':1}):
            with self.subTest(params=params),self.assertRaises(ValueError):Settings(**params).validate()
    def test_correction_interpolation_and_bounds(self):
        c=Curve([(100,2),(10000,6)])
        self.assertAlmostEqual(c.at(1000),4);self.assertEqual(c.at(10000),6)
        with self.assertRaises(ValueError):c.at(10)
        for pts in ([(100,2),(100,3)],[(100,float('nan')),(10000,0)]):
            with self.assertRaises(ValueError):Curve(pts)
    def test_demo_finite(self):
        d=Demo();d.configure(Settings());self.assertTrue(all(math.isfinite(d.measure(f)) for f in Settings().frequencies()))
    def test_single_parser_rejects_extra_detector_or_sentinel(self):
        class Fake:
            def write_str_with_opc(self,*args):pass
        d=ESR.__new__(ESR);d.io=Fake();d.s=Settings();d.write=lambda _:None;d.log=lambda _:None
        for invalid in ('1,2','nan','9.9E37'):
            d.query=lambda c: '1000000' if c=='FREQ:CENT?' else invalid
            with self.assertRaises(RuntimeError):d.measure(1000000)
        d.query=lambda c: '1000000' if c=='FREQ:CENT?' else '42.5'
        self.assertEqual(d.measure(1000000),42.5)
    def test_frequency_mismatch_rejected(self):
        d=ESR.__new__(ESR);d.write=lambda _:None;d.query=lambda _:'9999990'
        with self.assertRaises(RuntimeError):d.measure(1000000)

if __name__=='__main__':unittest.main()
