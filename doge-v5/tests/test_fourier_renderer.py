from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS))

from PIL import Image, ImageChops

from doge_playground.fourier import FourierRenderer


_CJK_FONTS = (
    Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/google-droid/DroidSansFallback.ttf"),
)


class FourierRendererTests(unittest.TestCase):
    @unittest.skipUnless(any(path.exists() for path in _CJK_FONTS), "CJK font not installed")
    def test_text_chinese_uses_large_real_font_and_keeps_all_frames(self):
        path, stats = FourierRenderer.from_text(
            "豆", mode="merge", vectors=32, frames=40, samples=512
        )
        try:
            with Image.open(path) as image:
                self.assertEqual(stats.frames, 40)
                self.assertEqual(image.n_frames, 40)
                image.seek(image.n_frames - 1)
                frame = image.convert("RGB")
                background = Image.new("RGB", frame.size, (252, 252, 250))
                bbox = ImageChops.difference(frame, background).getbbox()
                self.assertIsNotNone(bbox)
                assert bbox is not None
                self.assertGreater(bbox[2] - bbox[0], 250)
                self.assertGreater(bbox[3] - bbox[1], 250)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_text_font_candidates_include_production_cjk_location(self):
        source = Path("plugins/doge_playground/fourier.py").read_text(encoding="utf-8")
        self.assertIn("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc", source)
        self.assertNotIn("font=ImageFont.load_default()", source)


if __name__ == "__main__":
    unittest.main()
