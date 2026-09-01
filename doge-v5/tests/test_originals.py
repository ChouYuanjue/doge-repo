import json, random, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"plugins"
sys.path.insert(0,str(ROOT))
from doge_shared.alchemy import AlchemyBook, parse, split_recipe
from doge_shared.arena import draw, scene
from doge_shared.signal import new_game

class AlchemyTests(unittest.TestCase):
    def test_split_preserves_spaces(self):
        self.assertEqual(split_recipe("large language model + 月球 电梯"),("large language model","月球 电梯"))
    def test_book_commutative_and_persistent(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"book.json"
            d=parse(json.dumps({"name":"雨库","emoji":"🌧️","description":"一个会在下雨时自动扩容的数据库。","rarity":"rare","tags":["数据库","天气"]},ensure_ascii=False),"雨天","数据库","1")
            book=AlchemyBook(path); book.add(d)
            self.assertEqual(book.get("数据库","雨天").name,"雨库")
            self.assertEqual(AlchemyBook(path).count(),1)

class SignalTests(unittest.TestCase):
    def test_signal(self):
        g=new_game("hard",random.Random(7))
        self.assertNotEqual(g.encoded,g.answer)
        self.assertTrue(g.check(g.answer)); self.assertFalse(g.check(g.answer+"x"))
        self.assertEqual(len(g.layers),4)

class ArenaTests(unittest.TestCase):
    def test_seeded_card_and_scene(self):
        self.assertEqual(draw(random.Random(42)),draw(random.Random(42)))
        s=scene(random.Random(9)); self.assertTrue(s.location and s.objective and s.anomaly)
        self.assertIn("能力：",draw(random.Random(1)).render())

if __name__=="__main__": unittest.main()
