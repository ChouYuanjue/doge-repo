from __future__ import annotations

import asyncio
import html
import json
import os
import re
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import aiohttp
from bs4 import BeautifulSoup


class LookupError(RuntimeError):
    pass


UA = "Doge-v5/5.6 (+https://github.com/ChouYuanjue/doge-repo)"
QLEVER = "https://qlever.dev/api/wikidata"


async def _json(url, params=None, timeout=12, headers=None):
    t = aiohttp.ClientTimeout(total=timeout, connect=min(5, timeout), sock_read=max(4, timeout - 2))
    hs = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    async with aiohttp.ClientSession(timeout=t, headers=hs) as s:
        async with s.get(url, params=params) as r:
            body = await r.text()
            if r.status >= 400:
                raise LookupError(f"HTTP {r.status}: {body[:500]}")
            try:
                return json.loads(body)
            except Exception as exc:
                raise LookupError("远端没有返回可解析 JSON") from exc


async def _text(url, params=None, headers=None, timeout=15):
    hs = {"User-Agent": UA, "Accept": "text/plain,text/html,*/*", **(headers or {})}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=hs) as s:
        async with s.get(url, params=params) as r:
            body = await r.text()
            if r.status >= 400:
                raise LookupError(f"HTTP {r.status}: {body[:500]}")
            return body


ANYSEARCH_ENDPOINT = "https://api.anysearch.com/mcp"


async def _anysearch_call(tool_name: str, arguments: dict, timeout: int = 22) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    t = aiohttp.ClientTimeout(total=timeout, connect=min(6, timeout), sock_read=max(8, timeout - 2))
    async with aiohttp.ClientSession(timeout=t, headers={"Content-Type": "application/json", "User-Agent": UA}) as session:
        try:
            async with session.post(ANYSEARCH_ENDPOINT, json=payload) as response:
                body = await response.text()
                if response.status >= 400:
                    raise LookupError(f"AnySearch HTTP {response.status}: {body[:500]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise LookupError(f"AnySearch unavailable: {exc}") from exc
    try:
        data = json.loads(body)
    except Exception as exc:
        raise LookupError("AnySearch returned invalid JSON") from exc
    if data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise LookupError(f"AnySearch error: {msg}")
    for item in ((data.get("result") or {}).get("content") or []):
        if isinstance(item, dict) and item.get("type") == "text":
            return str(item.get("text") or "").strip()
    raise LookupError("AnySearch returned no text results")


def _validate_public_url(url: str) -> str:
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LookupError("网页提取只接受公开 http/https URL")
    host = parsed.hostname.lower().strip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise LookupError("拒绝访问本地/私有地址")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise LookupError("网页域名无法解析") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise LookupError("拒绝访问本地、私网、链路本地或保留地址")
    return raw


async def _bing_web_search(query: str, max_results: int = 6) -> str:
    body = await _text(
        "https://cn.bing.com/search",
        {"q": query, "count": max(3, min(int(max_results), 10)), "setlang": "en-US"},
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"},
        timeout=12,
    )
    soup = BeautifulSoup(body, "lxml")
    rows = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a or not a.get("href"):
            continue
        title = a.get_text(" ", strip=True)
        url = str(a.get("href") or "").strip()
        p = li.select_one(".b_caption p") or li.select_one("p")
        snippet = p.get_text(" ", strip=True) if p else ""
        if title and url.startswith(("http://", "https://")):
            rows.append((title, url, snippet))
        if len(rows) >= max_results:
            break
    if not rows:
        raise LookupError("Bing public search returned no usable results")
    lines = [f"Web search · Bing public fallback · {len(rows)} results"]
    for i, (title, url, snippet) in enumerate(rows, 1):
        lines += ["", f"{i}. {title}", url]
        if snippet:
            lines.append(snippet[:700])
    return "\n".join(lines)


@dataclass
class WikiResult:
    title: str
    description: str
    extract: str
    url: str
    thumbnail: str = ""
    source: str = "Wikipedia"

    def format(self):
        xs = [f"{self.source} · {self.title}"]
        if self.description:
            xs.append(self.description)
        if self.extract:
            xs += ["", self.extract]
        if self.url:
            xs += ["", self.url]
        return "\n".join(xs)


def _strip_html(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _literal(value: str) -> str:
    # JSON string escaping is compatible with SPARQL string literals for the
    # characters we allow here.
    return json.dumps(value, ensure_ascii=False)


async def _qlever(query: str, timeout: int = 12) -> list[dict]:
    data = await _json(
        QLEVER,
        {"query": query},
        timeout=timeout,
        headers={"Accept": "application/sparql-results+json"},
    )
    return ((data.get("results") or {}).get("bindings") or [])


class LookupService:
    @staticmethod
    def _lang(lang):
        lang = (lang or "zh").lower().strip()
        if not lang.replace("-", "").isalpha() or len(lang) > 12:
            raise LookupError("非法语言代码")
        return lang

    @staticmethod
    async def _baike(q: str) -> WikiResult:
        url = "https://baike.baidu.com/item/" + quote(q.strip(), safe="")
        body = await _text(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 Doge-v5/5.6"})
        title_m = re.search(r"<title>(.*?)</title>", body, re.I | re.S)
        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', body, re.I | re.S)
        if not desc_m:
            # Attribute order is not guaranteed.
            desc_m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', body, re.I | re.S)
        title = _strip_html(title_m.group(1) if title_m else "").removesuffix("_百度百科")
        desc = _strip_html(desc_m.group(1) if desc_m else "")
        if not desc or desc.startswith("百度百科是一部内容开放"):
            raise LookupError("百度百科未找到可靠词条")
        return WikiResult(title or q, "", desc[:5000], url, source="百度百科")

    @classmethod
    async def wikipedia(cls, q, lang="zh"):
        q = (q or "").strip()
        lang = cls._lang(lang)
        if not q or len(q) > 300:
            raise LookupError("百科查询需为 1-300 字符")
        # Prefer the requested source when the deployment route can reach it.
        try:
            d = await _json(
                f"https://{lang}.wikipedia.org/w/api.php",
                {"action": "query", "list": "search", "srsearch": q, "srlimit": 1, "format": "json", "utf8": 1},
                timeout=4,
            )
            rows = ((d.get("query") or {}).get("search") or [])
            if not rows:
                raise LookupError("Wikipedia 未找到匹配条目")
            title = str(rows[0].get("title") or "")
            d = await _json(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title, safe='')}",
                timeout=4,
            )
            page = (((d.get("content_urls") or {}).get("desktop") or {}).get("page") or f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}")
            return WikiResult(
                str(d.get("title") or title),
                str(d.get("description") or ""),
                str(d.get("extract") or "")[:5000],
                page,
                ((d.get("thumbnail") or {}).get("source") or ""),
                "Wikipedia",
            )
        except (LookupError, aiohttp.ClientError, asyncio.TimeoutError):
            # Alibaba CN currently cannot reach Wikimedia reliably. Baidu Baike
            # is a real encyclopedia backend, not an LLM/static-data substitute.
            try:
                return await cls._baike(q)
            except (LookupError, aiohttp.ClientError, asyncio.TimeoutError):
                # Last real-source fallback: Wikidata description from QLever.
                item = await cls._find_entity(q, lang)
                return WikiResult(
                    item["label"],
                    item.get("description", ""),
                    item.get("description", ""),
                    f"https://qlever.dev/wikidata?query={quote(item['qid'])}",
                    source="Wikidata · QLever mirror",
                )

    @classmethod
    async def _find_entity(cls, q: str, lang: str) -> dict:
        q = q.strip()
        if re.fullmatch(r"Q\d+", q, re.I):
            qid = q.upper()
            query = f'''PREFIX wd: <http://www.wikidata.org/entity/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX schema: <http://schema.org/> SELECT ?label ?desc WHERE {{ wd:{qid} rdfs:label ?label . FILTER(lang(?label)="{lang}" || lang(?label)="en") OPTIONAL {{ wd:{qid} schema:description ?desc . FILTER(lang(?desc)="{lang}" || lang(?desc)="en") }} }} LIMIT 4'''
            rows = await _qlever(query)
            if not rows:
                raise LookupError("Wikidata/QLever 未找到实体")
            r = rows[0]
            return {"qid": qid, "label": r.get("label", {}).get("value", qid), "description": r.get("desc", {}).get("value", "")}

        langs = [lang]
        if lang != "en":
            langs.append("en")
        values = " ".join(f"{_literal(q)}@{x}" for x in langs)
        query = f'''PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX schema: <http://schema.org/>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT ?item ?label ?desc ?sitelinks WHERE {{
  VALUES ?name {{ {values} }}
  VALUES ?p {{ rdfs:label skos:altLabel }}
  ?item ?p ?name .
  OPTIONAL {{ ?item rdfs:label ?label . FILTER(lang(?label)="{lang}" || lang(?label)="en") }}
  OPTIONAL {{ ?item schema:description ?desc . FILTER(lang(?desc)="{lang}" || lang(?desc)="en") }}
  OPTIONAL {{ ?item wikibase:sitelinks ?sitelinks }}
}} ORDER BY DESC(?sitelinks) LIMIT 8'''
        rows = await _qlever(query)
        if not rows:
            raise LookupError("Wikidata/QLever 未找到实体；请尝试更精确的正式名称或 Q-ID")
        r = rows[0]
        uri = r.get("item", {}).get("value", "")
        qid = uri.rsplit("/", 1)[-1]
        if not re.fullmatch(r"Q\d+", qid):
            raise LookupError("Wikidata/QLever 返回了非法实体 ID")
        return {
            "qid": qid,
            "label": r.get("label", {}).get("value") or q,
            "description": r.get("desc", {}).get("value", ""),
        }

    @classmethod
    async def wikidata(cls, q, lang="zh"):
        q = (q or "").strip()
        lang = cls._lang(lang)
        if not q or len(q) > 300:
            raise LookupError("Wikidata 查询需为 1-300 字符")
        hit = await cls._find_entity(q, lang)
        qid = hit["qid"]
        props = {
            "P31": "性质/类型", "P279": "上位类", "P17": "国家/地区", "P131": "行政区",
            "P361": "属于", "P106": "职业", "P108": "雇主", "P69": "教育经历",
            "P569": "出生日期", "P570": "逝世日期", "P571": "成立/创建", "P576": "解散/终止",
            "P625": "坐标", "P856": "官方网站",
        }
        values = " ".join(f"wdt:{p}" for p in props)
        query = f'''PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?p ?value ?valueLabel WHERE {{
  VALUES ?p {{ {values} }}
  wd:{qid} ?p ?value .
  OPTIONAL {{ ?value rdfs:label ?valueLabel . FILTER(lang(?valueLabel)="{lang}" || lang(?valueLabel)="en") }}
}} LIMIT 100'''
        rows = await _qlever(query)
        by_pred = {f"http://www.wikidata.org/prop/direct/{k}": v for k, v in props.items()}
        grouped: dict[str, list[str]] = {}
        for row in rows:
            pred = row.get("p", {}).get("value", "")
            label = by_pred.get(pred)
            if not label:
                continue
            binding = row.get("value") or {}
            value = (row.get("valueLabel") or {}).get("value") or binding.get("value", "")
            if binding.get("type") == "uri" and value.startswith("http://www.wikidata.org/entity/"):
                value = value.rsplit("/", 1)[-1]
            value = str(value).lstrip("+").replace("T00:00:00Z", "")
            if value and value not in grouped.setdefault(label, []):
                grouped[label].append(value)
        lines = [f"Wikidata · QLever mirror · {hit['label']} ({qid})"]
        if hit.get("description"):
            lines.append(hit["description"])
        lines += [f"{k}：{'；'.join(v[:6])}" for k, v in grouped.items()]
        lines += ["", f"QLever: https://qlever.dev/wikidata · entity {qid}"]
        return "\n".join(lines)

    @staticmethod
    async def web_search(q: str, max_results: int = 6, freshness: str = "") -> str:
        q = str(q or "").strip()
        if not q or len(q) > 600:
            raise LookupError("网页查询需为 1-600 字符")
        count = max(2, min(int(max_results), 10))
        arguments = {"query": q, "max_results": count}
        if freshness:
            arguments["freshness"] = str(freshness)[:32]
        try:
            out = await _anysearch_call("search", arguments)
            return "Web search · AnySearch anonymous (no API key)\n" + out[:14000]
        except LookupError as primary:
            try:
                return await _bing_web_search(q, count)
            except LookupError as fallback:
                raise LookupError(f"网页检索失败：{primary}；fallback：{fallback}") from fallback

    @staticmethod
    async def web_extract(url: str) -> str:
        url = _validate_public_url(url)
        out = await _anysearch_call("extract", {"url": url}, timeout=26)
        if len(out) > 16000:
            out = out[:16000] + "\n…[正文截断]"
        return "Web extract · AnySearch anonymous (no API key)\n" + out

    @staticmethod
    async def wolfram(q, maxchars=3500, appid: str | None = None):
        q = (q or "").strip()
        appid = (appid or os.getenv("WOLFRAM_ALPHA_APPID", "")).strip()
        if not q or len(q) > 500:
            raise LookupError("Wolfram 查询需为 1-500 字符")
        if not appid:
            raise LookupError("未配置 Wolfram|Alpha AppID；可在 doge_math 插件配置中填写 wolfram_appid")
        # The official LLM API accepts AppID as the `appid` query parameter.
        # Keeping the credential out of headers/logging also makes this path easy
        # to share with the direct /math command and the generic lookup service.
        return (
            await _text(
                "https://www.wolframalpha.com/api/v1/llm-api",
                {
                    "input": q,
                    "appid": appid,
                    "maxchars": max(400, min(int(maxchars), 6000)),
                },
                None,
                25,
            )
        ).strip()

    @classmethod
    async def auto(cls, q, lang="zh"):
        a, b = await asyncio.gather(cls.wikipedia(q, lang), cls.wikidata(q, lang), return_exceptions=True)
        xs = []
        if isinstance(a, WikiResult):
            xs.append(a.format())
        if isinstance(b, str):
            xs.append(b)
        if not xs:
            raise LookupError("；".join(str(x) for x in (a, b) if isinstance(x, Exception)) or "没有找到结果")
        return "\n\n——\n\n".join(xs)
