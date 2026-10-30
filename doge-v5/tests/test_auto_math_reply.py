from __future__ import annotations
import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"plugins"))
data=sys.modules.setdefault("data",types.ModuleType("data"))
plugins=sys.modules.setdefault("data.plugins",types.ModuleType("data.plugins"))
plugins.__path__=[str(ROOT/"plugins")]
data.plugins=plugins

import astrbot.api.message_components as Comp
from doge_shared.auto_math_reply import AutoMathRenderer,split_latex_reply,has_latex_reply
from doge_core.main import DogeCore

FENCE=chr(96)*3

class AutoMathTests(unittest.IsolatedAsyncioTestCase):
    def test_detect_known_math_syntax_and_ignore_false_positives(self):
        for s in (
            r"积分 $\int_0^1 x^2\,dx$ 收敛",
            r"公式 \[E=mc^2\]，很好",
            r"显示 $$E=mc^2$$",
            r"此处 \(\frac12\) 是分式",
            r"\begin{align}a&=b\\c&=d\end{align}",
            r"分式 \frac{a}{b} 和其他文字",
        ):
            with self.subTest(s=s):
                self.assertTrue(has_latex_reply(s))
        for s in (
            "价格 $12 and $25",
            "纯文字 x^2 和 E=mc^2",
            FENCE+"latex\n$$x^2$$\n"+FENCE,
            "表达式在 "+chr(96)+"$a+b$"+chr(96)+" 行内代码中",
            "文本 \n"+FENCE+"\n\\frac{a}{b}\n"+FENCE+"\n",
        ):
            with self.subTest(s=s):
                self.assertFalse(has_latex_reply(s))

    def test_bare_macros_before_delimited_math_are_both_detected(self):
        spans=split_latex_reply(r"分式 \\frac{1}{2} 与 $x^2$")
        self.assertEqual([kind for kind,_,_ in spans if kind=="math"],["math","math"])

    async def test_real_png_preserves_text_formula_order(self):
        with tempfile.TemporaryDirectory() as td:
            renderer=AutoMathRenderer(Path(td))
            source=r"积分 $x^2$ 和 \[\frac{a}{b}\] 完成。"
            chain,has_image=await renderer.render_chain(
                [Comp.Plain(source)],onebot=True,markdown=False,
            )
            self.assertTrue(has_image)
            self.assertEqual([type(v).__name__ for v in chain],
                             ["Plain","Image","Plain","Image","Plain"])
            self.assertEqual(chain[0].text,"积分 ")
            self.assertEqual(chain[2].text," 和 ")
            self.assertEqual(chain[-1].text," 完成。")
            self.assertTrue(list((Path(td)/"auto-tex").rglob("*.png")))

    async def test_fallback_plain_and_no_external_network(self):
        with tempfile.TemporaryDirectory() as td:
            renderer=AutoMathRenderer(Path(td))
            for source in (
                "只有普通文本和 2*3=6",
                "价格 $12 and $25，没问题",
                FENCE+"latex\n$$E=mc^2$$\n"+FENCE,
            ):
                chain,has_image=await renderer.render_chain(
                    [Comp.Plain(source)],onebot=True,markdown=False,
                )
                self.assertFalse(has_image)
                self.assertEqual(len(chain),1)
                expected=source.strip()
                if expected.startswith(FENCE):
                    expected="$$E=mc^2$$"  # QQ plain-text Markdown conversion removes code fences.
                self.assertEqual(chain[0].text.strip(),expected)

    async def test_outbound_decorator_renders_model_result_and_not_plugin_media(self):
        with tempfile.TemporaryDirectory() as td:
            core=object.__new__(DogeCore)
            core.auto_math_renderer=AutoMathRenderer(Path(td))
            class Result:
                def __init__(self,llm,text):
                    self.chain=[Comp.Plain(text)]
                    self.llm=llm
                    self.markdown=None
                def is_llm_result(self):return self.llm
                def is_model_result(self):return self.llm
                def use_markdown(self,value):self.markdown=value
            class Event:
                def __init__(self,result):self.result=result
                def get_platform_name(self):return "aiocqhttp"
                def get_result(self):return self.result
                def get_self_id(self):return "10000"
            result=Result(True,r"因此 \[E=mc^2\] 成立")
            await core.transport_markdown_result(Event(result))
            self.assertEqual(result.markdown,False)
            self.assertEqual([type(v).__name__ for v in result.chain],["Plain","Image","Plain"])
            plugin=Result(False,r"原始 $x^2$")
            await core.transport_markdown_result(Event(plugin))
            self.assertEqual(len(plugin.chain),1)
            self.assertEqual(plugin.chain[0].text,r"原始 $x^2$")
