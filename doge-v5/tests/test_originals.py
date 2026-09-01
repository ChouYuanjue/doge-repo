import hashlib, json, random, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"plugins"
sys.path.insert(0,str(ROOT))
from doge_shared.alchemy import AlchemyBook, parse, split_recipe
from doge_arena.arena_engine import ArenaStore, POWERS, capacity, classic_judge_prompts, draw_chaos, draw_legacy, scene
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
    def test_all_238_v4_wp_cards_are_preserved_byte_for_byte(self):
        repo=Path(__file__).resolve().parents[2]
        old=(repo/"doge-v4/wp/wp.json").read_bytes()
        new=(repo/"doge-v5/plugins/doge_arena/resources/wp_legacy.json").read_bytes()
        self.assertEqual(hashlib.sha256(new).hexdigest(),"63e6379b6b5ce9438c87d947d093f220a627d9836f9878410f8b9f27426a0b04")
        self.assertEqual(new,old)
        self.assertEqual(len(POWERS),238)
        raw=json.loads(old)
        self.assertEqual([(p.name,p.description) for p in POWERS],[(x["name"],x["description"]) for x in raw])

    def test_default_draw_is_original_wp_not_generic_prototype(self):
        card=draw_legacy(random.Random(42))
        self.assertEqual(len(card.powers),1)
        self.assertEqual(card.mode,"legacy")
        self.assertIn(card.powers[0],POWERS)
        self.assertIn(card.powers[0].description,card.render())
        generic={"局部重力编辑","颜色冻结","概率借款","字幕实体化","错误撤销","影子交换","声音折叠","摩擦税","星期偏移","概念磁铁","尺寸错觉","排队权"}
        self.assertTrue(generic.isdisjoint({p.name for p in POWERS}))

    def test_chaos_uses_distinct_original_cards_and_large_space(self):
        card=draw_chaos(random.Random(7),count=3)
        self.assertEqual(len(card.powers),3)
        self.assertEqual(len({p.name for p in card.powers}),3)
        self.assertTrue(all(p in POWERS for p in card.powers))
        c=capacity()
        self.assertEqual(c["legacy"],238)
        self.assertGreater(c["total_cards"],100_000_000_000)
        self.assertGreaterEqual(c["scenes"],40_000)

    def test_classic_fight_prompt_preserves_weak_power_semantics(self):
        a=draw_legacy(random.Random(1)); b=draw_legacy(random.Random(2))
        system,prompt=classic_judge_prompts("甲",a,"乙",b)
        self.assertIn(a.powers[0].description,prompt)
        self.assertIn(b.powers[0].description,prompt)
        self.assertIn("不得擅自增加能力",prompt)
        self.assertIn("原文字面",system)

    def test_store_roundtrip_and_v53_migration(self):
        with tempfile.TemporaryDirectory() as td:
            st=ArenaStore(Path(td)/"arena.json")
            card=draw_chaos(random.Random(3),count=2); st.set("s","u",card)
            self.assertEqual(st.get("s","u").to_json(),card.to_json())
            st.cards["s␟old"]={"title":"旧原型","power":"旧能力","trigger":"旧触发","cost":"旧代价","quirk":"旧怪癖"}
            migrated=st.get("s","old")
            self.assertEqual(migrated.mode,"prototype")
            self.assertIn("旧能力",migrated.render())

    def test_scene_is_seed_reproducible(self):
        self.assertEqual(scene(random.Random(9)),scene(random.Random(9)))

if __name__=="__main__": unittest.main()
