from __future__ import annotations
import asyncio
from pathlib import Path
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,StarTools,register
from data.plugins.doge_shared.presentation import file_result,image_result,images_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head
from data.plugins.doge_shared.typeset import TypesetDependencyError,TypesetError,render_tex,render_typst,tex_help,typst_help
from data.plugins.doge_shared.markdown_typeset import markdown_help,render_markdown,render_snippet,snippet_help
from data.plugins.doge_shared.help_service import format_cli_error

@register('doge_typeset','runnel','TeX 与 Typst 群聊排版','5.3.0')
class DogeTypeset(Star):
 def __init__(self,context:Context): super().__init__(context); self.data_dir=StarTools.get_data_dir('doge_typeset')

 @filter.command('md')
 async def markdown(self,event:AstrMessageEvent):
  paths=[]
  try:
   payload=command_payload(event.message_str,'md')
   if not payload.strip() or payload.strip().lower() in {'help','?'}:
    yield text_result(event,markdown_help(),markdown=False); return
   mode='card'; parts=split_head(payload,1)
   if parts and parts[0].lower() in {'card','doc','pdf'}:
    mode=parts[0].lower()
    if len(parts)<2:
     yield text_result(event,markdown_help(),markdown=False); return
    payload=parts[1]
   paths,caption=await asyncio.to_thread(render_markdown,self.data_dir,payload,mode)
   if mode=='pdf':
    yield file_result(event,paths[0],name='doge-markdown.pdf',caption=caption)
   else:
    yield images_result(event,paths,caption)
  except (TypesetError,TypesetDependencyError,ValueError) as e: yield text_result(event,str(e),markdown=False)
  except Exception as e: logger.warning(f'doge md failed: {e}'); yield text_result(event,format_cli_error('md', e),markdown=False)
  finally:
   for p in paths: Path(p).unlink(missing_ok=True)

 @filter.command('snippet')
 async def snippet(self,event:AstrMessageEvent):
  path=None
  try:
   payload=command_payload(event.message_str,'snippet')
   if not payload.strip() or payload.strip().lower() in {'help','?'}:
    yield text_result(event,snippet_help(),markdown=False); return
   parts=split_head(payload,1)
   if len(parts)<2:
    yield text_result(event,snippet_help(),markdown=False); return
   lang,rest=parts[0].lower(),parts[1]
   title=''; highlight=''
   # Options are parsed only at the front so code itself remains byte-for-byte
   # intact after the option prefix. Use `--` to disambiguate code beginning
   # with an option-looking token.
   import re
   while True:
    m=re.match(r'^\s*--(title|hl)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))\s*',rest,re.S)
    if not m: break
    value=next(x for x in m.groups()[1:] if x is not None)
    if m.group(1)=='title': title=value
    else: highlight=value
    rest=rest[m.end():]
   if rest.startswith('-- '): rest=rest[3:]
   path,caption=await asyncio.to_thread(render_snippet,self.data_dir,rest,language=lang,title=title,highlight=highlight)
   yield image_result(event,path,caption)
  except (TypesetError,TypesetDependencyError,ValueError) as e: yield text_result(event,str(e),markdown=False)
  except Exception as e: logger.warning(f'doge snippet failed: {e}'); yield text_result(event,format_cli_error('snippet', e),markdown=False)
  finally:
   if path is not None: Path(path).unlink(missing_ok=True)

 @filter.command('tex')
 async def tex(self,event:AstrMessageEvent):
  path=None
  try:
   payload=command_payload(event.message_str,'tex')
   if not payload.strip() or payload.strip().lower() in {'help','?'}: yield text_result(event,tex_help(),markdown=False); return
   mode='smart'; parts=split_head(payload,1)
   if parts and parts[0].lower() in {'smart','native','local'}:
    mode=parts[0].lower()
    if len(parts)<2: yield text_result(event,tex_help(),markdown=False); return
    payload=parts[1]
   path,caption=await render_tex(self.data_dir,payload,mode); yield image_result(event,path,caption)
  except (TypesetError,TypesetDependencyError,ValueError) as e: yield text_result(event,str(e),markdown=False)
  except Exception as e: logger.warning(f'doge tex failed: {e}'); yield text_result(event,format_cli_error('tex', e),markdown=False)
  finally:
   if path is not None: Path(path).unlink(missing_ok=True)
 @filter.command('typst')
 async def typst(self,event:AstrMessageEvent):
  paths=[]
  try:
   payload=command_payload(event.message_str,'typst')
   if not payload.strip() or payload.strip().lower() in {'help','?'}: yield text_result(event,typst_help(),markdown=False); return
   mode='card'; parts=split_head(payload,1)
   if parts and parts[0].lower() in {'math','card','doc','chat'}:
    mode=parts[0].lower()
    if len(parts)<2: yield text_result(event,typst_help(),markdown=False); return
    payload=parts[1]
   paths,caption=await asyncio.to_thread(render_typst,self.data_dir,payload,mode); yield images_result(event,paths,caption)
  except (TypesetError,TypesetDependencyError,ValueError) as e: yield text_result(event,str(e),markdown=False)
  except Exception as e: logger.warning(f'doge typst failed: {e}'); yield text_result(event,format_cli_error('typst', e),markdown=False)
  finally:
   for p in paths: Path(p).unlink(missing_ok=True)
