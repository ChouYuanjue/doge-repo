"""Science second-pass real-computation tests, including non-demo inputs.

No benchmark asserts visual similarity. Tests verify independently computed
properties, parameter sensitivity, rejection of unsupported claims and
genuinely executed numerical / symbolic outputs.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
from doge_shared.visual_lab import LabError,render
from doge_shared.math_knot import knot_invariant,_calculate
from doge_shared.science_expression import compute
from doge_shared.capabilities import operation_by_id


class KnotInvariants(unittest.TestCase):
    def test_distinct_real_knot_invariants(self):
        a=asyncio.run(knot_invariant("3_1"))
        b=asyncio.run(knot_invariant("4_1"))
        c=asyncio.run(knot_invariant("7_2",poly="det"))
        self.assertIn("行列式 |Δ(-1)| = 3",a)
        self.assertIn("行列式 |Δ(-1)| = 5",b)
        self.assertIn("行列式 |Δ(-1)| = 11",c)
        self.assertIn("Jones",a)
        self.assertNotEqual(a,b)
        self.assertIn("KnotPy",a)

    def test_planar_diagram_matches_named_trefoil(self):
        pd="pd [[1,5,2,4],[3,1,4,6],[5,3,6,2]]"
        answer=asyncio.run(knot_invariant(pd,"all"))
        self.assertIn("行列式 |Δ(-1)| = 3",answer)
        self.assertIn("t**2 - t + 1",answer)

    def test_reject_injection_and_malformed_pd(self):
        bad=["__import__('os').system('id')","pd __import__('os')",
             "pd [[1,2,3,foo]]", "not_a_knot", "99_999999999"]
        for x in bad:
            with self.subTest(x=x),self.assertRaises((ValueError,RuntimeError)):
                _calculate(x)
        with self.assertRaises(ValueError):
            _calculate("3_1","__class__")


class RealScientificRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory_obj=tempfile.TemporaryDirectory(prefix="doge-science2-")
        cls.directory=Path(cls.directory_obj.name)
    @classmethod
    def tearDownClass(cls):
        cls.directory_obj.cleanup()

    def call(self,payload:str):
        file,caption=render(self.directory,payload)
        self.assertTrue(file.is_file(),payload)
        self.assertGreater(file.stat().st_size,800)
        with Image.open(file) as im:
            self.assertGreater(im.width,120)
            self.assertGreater(im.height,120)
            im.verify()
        return hashlib.sha256(file.read_bytes()).hexdigest(),caption

    def test_fem_plate_changes_with_boundary_shape_and_materials(self):
        a,sa=self.call("chladni --shape square --bc clamped --mode 3 --refine 2 --thickness .001")
        b,sb=self.call("chladni --shape circle --bc simply --mode 3 --refine 2 --thickness .002")
        self.assertNotEqual(a,b)
        self.assertIn("scikit-fem",sa)
        self.assertIn("Kirchhoff",sb)
        self.assertRegex(sa,r"频率≈[0-9.]+ Hz")
        _,sc=self.call("chladni 5 3")
        self.assertIn("振型叠加",sc)

    def test_pde_uses_arbitrary_sources_and_initial_conditions(self):
        a,sa=self.call("pde poisson --f 'sin(pi*x)*sin(pi*y)' --shape lshape --refine 2")
        b,sb=self.call("pde poisson --f '4*sin(pi*x)*sin(pi*y)' --shape lshape --refine 2")
        self.assertNotEqual(a,b)
        self.assertIn("源函数",sa) if "源函数" in sa else self.assertIn("sin(pi*x)",sa)
        self.assertIn("scikit",sb) if "scikit" in sb else self.assertIn("二维线性三角有限元",sb)
        self.call("pde heat --init 'exp(-50*((x-.3)^2+(y-.5)^2))' --time .2 --steps 10")
        _,c=self.call("pde eigen --shape circle --mode 4 --refine 2")
        self.assertRegex(c,r"λ≈[0-9.]+")

    def test_custom_quantum_potential_changes_eigenvalues(self):
        _,a=self.call("well --potential 0 --n 3 --size 300")
        _,b=self.call("well --potential '50*(x-.5)^2' --n 3 --size 300")
        def extract(c):
            return float(re.search(r"E_n≈([0-9.eE+-]+)",c).group(1))
        e0,e1=extract(a),extract(b)
        self.assertAlmostEqual(e0,math.pi**2*9/2,delta=.03)
        self.assertGreater(e1,e0)
        self.assertIn("归一化积分≈1",a)

    def test_aperture_and_multi_lens_optics(self):
        a,_=self.call("diffraction --aperture 'exp(-(x/.25)^2)' --wavelength .5")
        b,_=self.call("diffraction --aperture 'exp(-(x/.4)^2)' --wavelength .5")
        self.assertNotEqual(a,b)
        _,c=self.call("lens --elements 'space:1;lens:.5;space:.7' --rays '0.1,0;0,0.03'")
        self.assertIn("总 ABCD",c)
        self.assertIn("det≈1",c)

    def test_mixed_qubit_state_and_boost_actual_invariants(self):
        _,a=self.call("bloch --rho '0.5,0,0,0.5'")
        self.assertIn("Tr(ρ²)=0.5",a)
        _,b=self.call("bloch --bloch 0,0,1 --gates 'H;Rz:180'")
        self.assertIn("Tr(ρ²)=1",b)
        _,c=self.call("relativity --beta 0.4 --events '1,0;2,1'")
        self.assertIn("保持不变",c)
        self.assertIn("原始 (ct,x)",c)

    def test_sandpile_exact_stabilization_and_custom_sites(self):
        _,a=self.call("sandpile --sites '0,0,3000;4,5,1000' --size 61")
        self.assertIn("真正稳定化",a)
        self.assertIn("最终所有格点高度均 <=3",a)
        self.assertIn("初始沙粒 4000",a)
        with self.assertRaises(LabError):
            render(self.directory,"sandpile --grains 1000000 --maxiter 100 --size 61")

    def test_arbitrary_non_gallery_patterns(self):
        for s in (
           "moire --angle1 12 --angle2 30 --spacing1 19 --spacing2 20 --size 180",
           "phyllotaxis --angle 138 --growth .7 --jitter 1.5 --seed 12",
           "beats --tones '7,1,0;8.4,.5,80;22,.1,0' --rate 1200 --seconds 1",
           "number ulam --size 51 --start 13 --step 2",
           "number mod --points 120 --expr 'x^2+3*x'",
        ):
            with self.subTest(s=s):
                self.call(s)
        a,_=self.call("number mod --points 120 --expr 'x^2+3*x'")
        b,_=self.call("number mod --points 120 --expr 'x^3+2'")
        self.assertNotEqual(a,b)

    def test_reject_ignored_or_impossible_science_config(self):
        for s in (
            "chladni --shape fake --mode 3",
            "pde eigen --shape triangle",
            "pde eigen --diffusion 2",
            "pde poisson --time 2",
            "pde heat --f 2",
            "pde poisson --shape circle --refine 5",
            "well --potential 'open(1)'",
            "diffraction --aperture 'x' --slits '0,1,1,0'",
            "lens --elements 'space:1' --focal 2",
            "bloch --bloch 2,0,0",
            "bloch --bloch 0.1,0.2,0.3 --theta 30",
            "bloch --rho '1,1,0,0'",
            "sandpile --boundary wrap",
            "number mod --start 11",
            "number ulam --points 300",
        ):
            with self.subTest(s=s), self.assertRaises((ValueError,LabError)):
                render(self.directory,s)


class ScienceCatalog(unittest.TestCase):
    def test_new_capabilities_listed(self):
        for name in ("math.knot","lab.pde","lab.chladni","lab.well","lab.bloch","lab.sandpile","lab.moire"):
            with self.subTest(name=name):
                self.assertIsNotNone(operation_by_id(name))


if __name__ == "__main__":
    unittest.main()
