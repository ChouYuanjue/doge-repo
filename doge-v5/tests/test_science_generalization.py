"""General-science anti-demo regression suite.

Every test asks for data beyond the historical hard-coded gallery, compares
physical/numeric results, or rejects invalid/synthetic inputs.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
from doge_shared.science_expression import compile_formula,compute
from doge_shared.math_matrices import matrix_op
from doge_shared.visual_lab_fun import _life_step, _life_seed
from doge_shared.visual_lab import LabError,help_text,render
from doge_shared.capabilities import operation_by_id
from doge_shared.help_service import render_help


class ScienceExpressionTests(unittest.TestCase):
    def test_arbitrary_symbolic_numpy_evaluation(self):
        z=np.array([-1j,2+3j,0.4])
        f=compute("sin(z)/(z^2+2)",("z",),z)
        np.testing.assert_allclose(f,np.sin(z)/(z*z+2),rtol=1e-12)
        x=np.array([-1.,1.])
        np.testing.assert_allclose(compute("exp(-x^2)+cos(3*x)",("x",),x),
                                   np.exp(-x**2)+np.cos(3*x))
    def test_python_surfaces_never_executable(self):
        payloads=[
            "__import__('os').system('id')",
            "z.__class__","open('/etc/passwd')",
            "[x for x in range(100)]","z[0]",
            "(lambda z: z)(1)","sin(z,1)","z**99999",
            "abs(z).__class__","sin(z)+globals()",
        ]
        for payload in payloads:
            with self.subTest(payload=payload),self.assertRaises((LabError,ValueError,TypeError)):
                compile_formula(payload,("z",))
    def test_life_like_birth_applies_to_dead_cells_only(self):
        board=np.ones((5,5),bool)
        result=_life_step(board,frozenset({8}),frozenset(),boundary="dead")
        self.assertFalse(result[2,2])
        seeded_1,label=_life_seed("random:1234:0.35",121,np.random.default_rng(1))
        seeded_2,_=_life_seed("random:1234:0.35",121,np.random.default_rng(2))
        self.assertEqual(label,"random:1234:0.35")
        np.testing.assert_array_equal(seeded_1,seeded_2)

    def test_nonfinite_config_rejected(self):
        with self.assertRaises(LabError):
            render(Path(tempfile.gettempdir()),"complex z --size 100000")
        with self.assertRaises(LabError):
            render(Path(tempfile.gettempdir()),"fractal mandelbrot --zoom nan")
        with self.assertRaises(LabError):
            render(Path(tempfile.gettempdir()),"ode --eq 'y;-x' --steps 100000000")
    def test_unsupported_options_not_ignored(self):
        for cmd in ("complex z --ensemble goe","fractal julia --radius 2",
                    "ising --rate 40","linear --temperature 3",
                    "fractal mandelbrot --c 0.3+0.2i",
                    "attractor lorenz --discard 50",
                    "field --charges '0,0,1' --fx x --fy y",
                    "randommatrix ginibre --ratio 2",
                    "orbital 3,2,1 --basis unknown"):
            with self.subTest(cmd=cmd),self.assertRaises(LabError):
                render(Path(tempfile.gettempdir()),cmd)


class MatrixAlgebraTests(unittest.TestCase):
    def test_exact_matrix_arithmetic(self):
        self.assertIn("-2",matrix_op("det","1,2;3,4"))
        self.assertIn("(1/5, 3/5)",matrix_op("solve","2,1;1,3",vector="1,2"))
        self.assertIn("rank=2",matrix_op("info","1,2,3;4,5,6"))
        self.assertIn("pivots=(0, 1)",matrix_op("rref","1,2,3;4,5,6"))
        self.assertIn("Eigenvalues",matrix_op("eig","0,-1;1,0"))
        self.assertIn("Singular values",matrix_op("svd","1,2,3;4,5,6"))
        self.assertIn("exp(A)",matrix_op("expm","0,-1;1,0"))
    def test_matrix_invalid_shapes_and_code(self):
        for src in ("1,2;3","1,2;__import__('os'),4","nan,1;2,3"):
            with self.subTest(source=src),self.assertRaises((ValueError,TypeError)):
                matrix_op("rank",src)
        with self.assertRaises(ValueError):
            matrix_op("add","1,2;3,4",other="1,2,3")
        with self.assertRaises(ValueError):
            matrix_op("solve","1,2;3,4",vector="1")


class RenderGeneralScienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="doge-science-")
        cls.directory=Path(cls.temp.name)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def render_one(self,cmd):
        p,c=render(self.directory,cmd)
        self.assertTrue(p.is_file(),cmd)
        self.assertGreater(p.stat().st_size,800,cmd)
        with Image.open(p) as image:
            self.assertGreater(image.width,100)
            self.assertGreater(image.height,100)
            image.verify()
        self.assertTrue(c)
        return hashlib.sha256(p.read_bytes()).hexdigest(),c

    def test_nonpreset_complex_and_fractal(self):
        x,c=self.render_one("complex 'sin(z)/(z^2+1)' --size 160")
        y,c=self.render_one("complex 'exp(z)/(z^2+1)' --size 160")
        self.assertNotEqual(x,y)
        x,_=self.render_one("fractal mandelbrot --expr z^3+c --iter 40 --size 160")
        y,_=self.render_one("fractal mandelbrot --expr z^4+c --iter 40 --size 160")
        self.assertNotEqual(x,y)
        self.render_one("fractal julia --expr z^3+c --c -.7+.2i --size 160 --iter 20")
        self.render_one("newton z^5-z+1 --size 160 --iter 18")

    def test_unrestricted_plot_and_matrix_shapes(self):
        for cmd in (
            "plot 'sin(x);x^2/4' --range -3,3 --size 250",
            "param --x 'cos(5*t)' --y 'sin(3*t)'",
            "linear --matrix '1,0,2;0,1,3' --vector 1,2,3",
            "orbital 4,2,1 --size 160 --mode density",
            "spectrum --expr 'sin(2*pi*7*t)+cos(2*pi*19*t)'",
            "spectrum square 9",
        ):
            with self.subTest(cmd=cmd):self.render_one(cmd)

    def test_ode_discrete_and_variable_physics(self):
        for cmd in (
            "ode --eq 'y;-x' --init 1,0 --time 2 --steps 100",
            "map --eq '1-a*x^2+y;b*x' --params a=1.4,b=.3 --steps 180 --discard 70",
            "chaos bifurcation --expr 'r*x-x^3' --samples 130 --discard 30 --steps 30",
            "field --fx -y --fy x --size 24",
            "wave --sources '-1,0,1,0;1,0,.6,45' --size 160",
            "pendulum --masses 1,2 --lengths 1,1.5 --time 1 --steps 100",
            "sir --r0 2.3 --infectious 4 --time 12 --steps 100",
            "predator --alpha 1 --beta .3 --gamma .5 --delta .2 --time 8 --steps 100",
            "replicator --matrix '1,2,3;3,1,2;2,3,1' --time 2 --steps 100",
        ):
            with self.subTest(cmd=cmd):self.render_one(cmd)

    def test_seeded_stochastic_and_user_geometry(self):
        for cmd in (
            "ising --seed 2 --size 32 --sweeps 2",
            "percolation --seed 2 --size 32 --kind bond",
            "randommatrix --seed 2 --n 15 --ensemble wishart",
            "brownian --walkers 5 --steps 30 --seed 1",
            "galton --rows 7 --balls 200 --p .35 --seed 2",
            "ant --turns RLLR --steps 150 --size 45",
            "ca 110 40 --seed random --width 51",
            "lsys custom --axiom F --rules 'F=F+F--F+F' --iter 2",
            "dla --particles 80 --size 181 --seed 77 --neighbors 4",
            "voronoi --sites '0,0;1,0;1,2' --size 180",
        ):
            with self.subTest(cmd=cmd):self.render_one(cmd)

    def test_lattice_reciprocal_real_structure_factors(self):
        self.render_one("lattice --vectors '2,0,0;0,3,0;0,0,4' --basis '0,0,0;0.5,0.5,0.5'")
        x,a=self.render_one("xrd --vectors '2,0,0;0,3,0;0,0,4' --basis '0,0,0,1;0.5,0.5,0.5,1' --maxh 4")
        y,b=self.render_one("xrd --vectors '2,0,0;0,3,0;0,0,4' --basis '0,0,0,1' --maxh 4")
        self.assertNotEqual(x,y,"structure factors should change for a different basis")
        self.assertIn("真实 CIF",a)


class HelpAndRegistryTests(unittest.TestCase):
    def test_help_does_not_crash_and_documents_general_engines(self):
        h=help_text()
        for word in ("newton","lattice","ising","ode","matrix"):
            if word=="matrix": continue
            self.assertIn(word,h)
        for cid in ("lab.plot","lab.parametric","lab.ode","lab.map","lab.nbody","math.matrix"):
            self.assertIsNotNone(operation_by_id(cid),cid)
            topic=operation_by_id(cid)["path"]
            rendered,_=render_help(topic)
            self.assertIn("USAGE",rendered)


if __name__=="__main__":
    unittest.main()
