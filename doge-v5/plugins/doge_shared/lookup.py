from __future__ import annotations
import asyncio, os
from dataclasses import dataclass
from urllib.parse import quote
import aiohttp

class LookupError(RuntimeError): pass
UA='Doge-v5/5.4 (+https://github.com/ChouYuanjue/doge-repo)'

async def _json(url, params=None, timeout=15):
    t=aiohttp.ClientTimeout(total=timeout,connect=6,sock_read=max(5,timeout-2))
    async with aiohttp.ClientSession(timeout=t,headers={'User-Agent':UA,'Accept':'application/json'}) as s:
        async with s.get(url,params=params) as r:
            if r.status>=400: raise LookupError(f'HTTP {r.status}: {(await r.text())[:500]}')
            return await r.json(content_type=None)

async def _text(url, params=None, headers=None, timeout=20):
    hs={'User-Agent':UA,'Accept':'text/plain'}; hs.update(headers or {})
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout),headers=hs) as s:
        async with s.get(url,params=params) as r:
            body=await r.text()
            if r.status>=400: raise LookupError(f'HTTP {r.status}: {body[:500]}')
            return body

@dataclass
class WikiResult:
    title:str; description:str; extract:str; url:str; thumbnail:str=''
    def format(self):
        xs=[f'Wikipedia · {self.title}']
        if self.description: xs.append(self.description)
        if self.extract: xs += ['',self.extract]
        if self.url: xs += ['',self.url]
        return '\n'.join(xs)

class LookupService:
    @staticmethod
    def _lang(lang):
        lang=(lang or 'zh').lower().strip()
        if not lang.replace('-','').isalpha() or len(lang)>12: raise LookupError('非法语言代码')
        return lang
    @classmethod
    async def wikipedia(cls,q,lang='zh'):
        q=(q or '').strip(); lang=cls._lang(lang)
        if not q or len(q)>300: raise LookupError('Wikipedia 查询需为 1-300 字符')
        d=await _json(f'https://{lang}.wikipedia.org/w/api.php',{'action':'query','list':'search','srsearch':q,'srlimit':1,'format':'json','utf8':1})
        rows=((d.get('query') or {}).get('search') or [])
        if not rows: raise LookupError('Wikipedia 未找到匹配条目')
        title=str(rows[0].get('title') or '')
        d=await _json(f'https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title,safe="")}')
        page=(((d.get('content_urls') or {}).get('desktop') or {}).get('page') or f'https://{lang}.wikipedia.org/wiki/{quote(title.replace(" ","_"))}')
        return WikiResult(str(d.get('title') or title),str(d.get('description') or ''),str(d.get('extract') or '')[:5000],page,((d.get('thumbnail') or {}).get('source') or ''))
    @staticmethod
    async def _labels(ids,lang):
        if not ids:return {}
        d=await _json('https://www.wikidata.org/w/api.php',{'action':'wbgetentities','ids':'|'.join(sorted(ids)[:40]),'props':'labels','languages':f'{lang}|en','format':'json'})
        out={}
        for q,e in (d.get('entities') or {}).items():
            ls=e.get('labels') or {}; v=(ls.get(lang) or ls.get('en') or {}).get('value')
            if v: out[q]=v
        return out
    @classmethod
    async def wikidata(cls,q,lang='zh'):
        q=(q or '').strip(); lang=cls._lang(lang)
        if not q or len(q)>300: raise LookupError('Wikidata 查询需为 1-300 字符')
        d=await _json('https://www.wikidata.org/w/api.php',{'action':'wbsearchentities','search':q,'language':lang,'uselang':lang,'limit':1,'format':'json'})
        rows=d.get('search') or []
        if not rows: raise LookupError('Wikidata 未找到实体')
        hit=rows[0]; qid=str(hit.get('id') or '')
        d=await _json(f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json'); claims=((d.get('entities') or {}).get(qid) or {}).get('claims') or {}
        props={'P31':'性质/类型','P279':'上位类','P17':'国家/地区','P131':'行政区','P361':'属于','P106':'职业','P108':'雇主','P69':'教育经历','P569':'出生日期','P570':'逝世日期','P571':'成立/创建','P576':'解散/终止','P625':'坐标','P856':'官方网站'}
        vals=[]; linked=set()
        for pid,label in props.items():
            for cl in (claims.get(pid) or [])[:5]:
                v=(((cl.get('mainsnak') or {}).get('datavalue') or {}).get('value'))
                if v is None: continue
                kind='raw'
                if isinstance(v,dict) and v.get('entity-type') and v.get('id'): kind='entity';v=str(v['id']);linked.add(v)
                elif isinstance(v,dict) and 'time' in v: kind='time';v=str(v.get('time') or '').lstrip('+').split('T',1)[0]
                elif isinstance(v,dict) and 'latitude' in v: kind='coord';v=f"{v['latitude']:.6g}, {v['longitude']:.6g}"
                elif isinstance(v,dict): continue
                vals.append((label,kind,v))
        labels=await cls._labels(linked,lang); grouped={}
        for label,kind,v in vals:
            x=labels.get(str(v),str(v)) if kind=='entity' else str(v)
            if x not in grouped.setdefault(label,[]): grouped[label].append(x)
        lines=[f"Wikidata · {hit.get('label') or qid} ({qid})"]
        if hit.get('description'): lines.append(str(hit['description']))
        lines += [f"{k}：{'；'.join(v[:5])}" for k,v in grouped.items()]
        lines += ['',f'https://www.wikidata.org/wiki/{qid}']; return '\n'.join(lines)
    @staticmethod
    async def wolfram(q,maxchars=3500):
        q=(q or '').strip(); appid=os.getenv('WOLFRAM_ALPHA_APPID','').strip()
        if not q or len(q)>500: raise LookupError('Wolfram 查询需为 1-500 字符')
        if not appid: raise LookupError('未配置 WOLFRAM_ALPHA_APPID；Wolfram 子功能保持关闭')
        return (await _text('https://www.wolframalpha.com/api/v1/llm-api',{'input':q,'maxchars':max(400,min(int(maxchars),6000))},{'Authorization':f'Bearer {appid}'},25)).strip()
    @classmethod
    async def auto(cls,q,lang='zh'):
        a,b=await asyncio.gather(cls.wikipedia(q,lang),cls.wikidata(q,lang),return_exceptions=True); xs=[]
        if isinstance(a,WikiResult): xs.append(a.format())
        if isinstance(b,str): xs.append(b)
        if not xs: raise LookupError('；'.join(str(x) for x in (a,b) if isinstance(x,Exception)) or '没有找到结果')
        return '\n\n——\n\n'.join(xs)
