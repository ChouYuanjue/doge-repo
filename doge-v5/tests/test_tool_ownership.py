from __future__ import annotations
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'plugins'))
from doge_shared.agent_tools import DogeMathTool,DogePaperTool,register_domain_tools

class FakeContext:
 def __init__(self): self.tools=[]
 def add_llm_tools(self,*tools):
  self.tools.extend(tools)
  for tool in tools: tool.handler_module_path='data.plugins.doge_shared.main'

class ToolOwnershipTests(unittest.TestCase):
 def test_domain_owner_overrides_shared_definition_module(self):
  c=FakeContext(); tools=register_domain_tools(c,'doge_math',DogeMathTool())
  self.assertEqual(tools[0].handler_module_path,'data.plugins.doge_math.main')
 def test_different_domains_do_not_share_lifecycle_path(self):
  c=FakeContext(); m=register_domain_tools(c,'doge_math',DogeMathTool())[0]; p=register_domain_tools(c,'doge_papers',DogePaperTool())[0]
  self.assertNotEqual(m.handler_module_path,p.handler_module_path)
  self.assertTrue(m.handler_module_path.startswith('data.plugins.doge_math.main'))
  self.assertTrue(p.handler_module_path.startswith('data.plugins.doge_papers.main'))

if __name__=='__main__': unittest.main()
