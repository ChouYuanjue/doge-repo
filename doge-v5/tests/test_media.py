from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

PLUGIN = Path(__file__).resolve().parents[1] / "plugins"
sys.path.insert(0, str(PLUGIN))

from doge_media.media_service import make_mirage


class MediaTests(unittest.TestCase):
    def test_local_mirage_renderer(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            front = td / "front.png"
            back = td / "back.png"
            a = Image.new("RGB", (160, 120), "white")
            da = ImageDraw.Draw(a); da.rectangle((20, 20, 140, 100), fill="black")
            a.save(front)
            b = Image.new("RGB", (160, 120), "black")
            db = ImageDraw.Draw(b); db.ellipse((25, 10, 135, 115), fill="white")
            b.save(back)
            out = asyncio.run(make_mirage(front, back, td / "out", "gray"))
            self.assertTrue(out.exists())
            with Image.open(out) as im:
                self.assertEqual(im.mode, "RGBA")
                self.assertEqual(im.size, (160, 120))
                self.assertGreater(max(im.getchannel("A").getextrema()), 0)


if __name__ == "__main__":
    unittest.main()
