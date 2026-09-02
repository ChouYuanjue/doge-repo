from __future__ import annotations

import sys
import tempfile
import asyncio
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from doge_shared.markdown_typeset import render_markdown, render_snippet
from doge_shared.typeset import TypesetError, _is_tex_document, render_tex


class MarkdownTypesetTests(unittest.TestCase):
    def test_card_renders_cjk_math_tasks_and_code(self):
        with tempfile.TemporaryDirectory() as td:
            source = (
                "# 标题\n\n> 引用 **粗体**，公式 $\\frac{1}{2}+\\sqrt{x}$\n\n"
                "- [x] 完成\n- [ ] 待办\n\n```python\nprint(42)\n```\n"
            )
            paths, caption = render_markdown(Path(td), source, "card")
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertIn("cmarker 0.1.10", caption)
            self.assertIn("MiTeX 0.2.7", caption)

    def test_pdf_is_real_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            paths, _ = render_markdown(Path(td), "# Report\n\nA short document.", "pdf")
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].read_bytes().startswith(b"%PDF"))

    def test_full_latex_document_is_detected(self):
        self.assertTrue(_is_tex_document(r"\documentclass{article}\begin{document}Hi\end{document}"))
        self.assertTrue(_is_tex_document(r"\begin{document}Hi\end{document}"))
        self.assertFalse(_is_tex_document(r"\frac{a}{b}"))

    @unittest.skipUnless((shutil.which("tectonic") or (Path.home()/".local/bin/tectonic").exists()) and shutil.which("bwrap"), "Tectonic+bwrap not installed")
    def test_full_latex_document_compiles_to_real_pdf(self):
        source = r"""\documentclass{article}
\usepackage{amsmath}
\begin{document}
A complete document.
\[\int_0^1 x^2\,dx=\frac13\]
\end{document}"""
        with tempfile.TemporaryDirectory() as td:
            path, caption = asyncio.run(render_tex(Path(td), source, "smart"))
            try:
                self.assertEqual(path.suffix, ".pdf")
                self.assertTrue(path.read_bytes().startswith(b"%PDF"))
                self.assertIn("Tectonic", caption)
            finally:
                path.unlink(missing_ok=True)

    @unittest.skipUnless((shutil.which("tectonic") or (Path.home()/".local/bin/tectonic").exists()) and shutil.which("bwrap"), "Tectonic+bwrap not installed")
    def test_full_latex_document_cannot_read_host_files(self):
        secret = Path("/tmp/doge-typeset-host-secret.tex")
        secret.write_text("HOST_SECRET_SHOULD_NEVER_BE_READ", encoding="utf-8")
        source = r"""\documentclass{article}
\begin{document}
Before.\input{/tmp/doge-typeset-host-secret.tex}After.
\end{document}"""
        try:
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(TypesetError):
                    asyncio.run(render_tex(Path(td), source, "doc"))
        finally:
            secret.unlink(missing_ok=True)

    def test_raw_typst_injection_is_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            # cmarker recognizes this extension only when raw-typst is enabled.
            # Rendering it must therefore not execute the injected panic.
            source = "# Safe\n\n<!--raw-typst #panic(\"injected\") -->\n\nStill safe."
            paths, _ = render_markdown(Path(td), source, "card")
            self.assertTrue(paths[0].read_bytes().startswith(b"\x89PNG"))


class SnippetTests(unittest.TestCase):
    def test_snippet_renders_language_title_and_highlights(self):
        with tempfile.TemporaryDirectory() as td:
            path, caption = render_snippet(
                Path(td),
                "def fib(n):\n    if n < 2:\n        return n\n    return fib(n-1)+fib(n-2)",
                language="python",
                title="fib.py",
                highlight="2-3",
            )
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertIn("Codly 1.3.0", caption)

    def test_invalid_highlight_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(TypesetError):
                render_snippet(Path(td), "one\ntwo", language="text", highlight="3")


if __name__ == "__main__":
    unittest.main()
