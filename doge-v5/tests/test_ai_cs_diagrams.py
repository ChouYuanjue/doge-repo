from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins' / 'doge_ai'))
sys.path.insert(0, str(ROOT / 'plugins' / 'doge_cs'))
sys.path.insert(0, str(ROOT / 'plugins'))

from ai_lab import render_bpe, render_grad
from cs_lab import render_pagerank, render_regex
from doge_shared.diagrams import DiagramError, render_graphviz, render_vegalite


class AILabTests(unittest.TestCase):
    def test_micrograd_graph(self):
        with tempfile.TemporaryDirectory() as td:
            p, caption = render_grad(Path(td), 'relu(x*y + x**2)', {'x':2, 'y':-1})
            self.assertTrue(p.read_bytes().startswith(b'\x89PNG'))
            self.assertIn('dout/dx=3', caption)

    def test_minbpe_chinese(self):
        with tempfile.TemporaryDirectory() as td:
            p, caption = render_bpe(Path(td), '大模型 tokenizer 大模型 tokenizer', 8)
            self.assertTrue(p.read_bytes().startswith(b'\x89PNG'))
            self.assertIn('minBPE', caption)


class CSLabTests(unittest.TestCase):
    def test_regex_pipeline(self):
        with tempfile.TemporaryDirectory() as td:
            ps, caption = render_regex(Path(td), '(a|b)*abb')
            self.assertEqual(len(ps), 3)
            self.assertTrue(all(p.read_bytes().startswith(b'\x89PNG') for p in ps))
            self.assertIn('min-DFA', caption)

    def test_pagerank(self):
        with tempfile.TemporaryDirectory() as td:
            p, caption = render_pagerank(Path(td), 'A>B,B>C,C>A,A>C')
            self.assertTrue(p.read_bytes().startswith(b'\x89PNG'))
            self.assertIn('3 nodes', caption)


class DiagramTests(unittest.TestCase):
    def test_graphviz_local(self):
        with tempfile.TemporaryDirectory() as td:
            p, caption = render_graphviz(Path(td), 'digraph G { A -> B }')
            self.assertTrue(p.read_bytes().startswith(b'\x89PNG'))
            self.assertIn('local', caption)

    def test_graphviz_local_files_are_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(DiagramError):
                render_graphviz(Path(td), 'digraph G { a [image="/etc/passwd"] }')

    def test_vegalite_inline(self):
        spec='{"data":{"values":[{"x":"A","y":2}]},"mark":"bar","encoding":{"x":{"field":"x"},"y":{"field":"y","type":"quantitative"}}}'
        with tempfile.TemporaryDirectory() as td:
            p, caption = render_vegalite(Path(td), spec)
            self.assertTrue(p.read_bytes().startswith(b'\x89PNG'))
            self.assertIn('Vega-Lite', caption)

    def test_vegalite_remote_data_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(DiagramError):
                render_vegalite(Path(td), '{"data":{"url":"https://example.com/a.csv"},"mark":"bar"}')


if __name__ == '__main__':
    unittest.main()
