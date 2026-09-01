from __future__ import annotations

import asyncio
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

import aiohttp


class AcademicError(RuntimeError):
    pass


UA = "Doge-v5-academic/0.1 (+group-chat research utility)"


def _doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.strip()


def _is_doi(value: str) -> bool:
    return bool(re.match(r"^10\.\d{4,9}/\S+$", _doi(value), flags=re.I))


def _clean(text: Any, limit: int = 500) -> str:
    if text is None:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", "", str(text))).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _names_crossref(authors: list[dict], limit: int = 5) -> str:
    names = []
    for a in authors[:limit]:
        name = " ".join(x for x in [a.get("given", ""), a.get("family", "")] if x).strip()
        if name:
            names.append(name)
    if len(authors) > limit:
        names.append("et al.")
    return ", ".join(names)


def _names_openalex(authorships: list[dict], limit: int = 5) -> str:
    names = [
        x.get("author", {}).get("display_name", "")
        for x in authorships[:limit]
        if x.get("author", {}).get("display_name")
    ]
    if len(authorships) > limit:
        names.append("et al.")
    return ", ".join(names)


async def _request_json(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    payload: dict | None = None,
    form: dict | None = None,
    headers: dict | None = None,
    timeout: float = 18.0,
) -> Any:
    h = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    t = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=t, headers=h) as session:
        async with session.request(method, url, params=params, json=payload, data=form) as resp:
            body = await resp.text()
            if resp.status >= 400:
                raise AcademicError(f"HTTP {resp.status}: {body[:260]}")
            try:
                return json.loads(body)
            except Exception as exc:
                raise AcademicError("远端没有返回可解析 JSON") from exc


async def _request_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 18.0,
) -> str:
    h = {"User-Agent": UA, **(headers or {})}
    t = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=t, headers=h) as session:
        async with session.get(url, params=params) as resp:
            body = await resp.text()
            if resp.status >= 400:
                raise AcademicError(f"HTTP {resp.status}: {body[:260]}")
            return body.strip()


async def _post_form_text(url: str, form: dict, timeout: float = 20.0) -> str:
    t = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=t, headers={"User-Agent": UA}) as session:
        async with session.post(url, data=form) as resp:
            body = await resp.text()
            if resp.status >= 400:
                raise AcademicError(f"HTTP {resp.status}: {body[:260]}")
            return body.strip()


class PaperService:
    @staticmethod
    def _oa_params(params: dict | None = None) -> dict:
        out = dict(params or {})
        key = os.getenv("OPENALEX_API_KEY", "").strip()
        if key:
            out["api_key"] = key
        return out

    @classmethod
    async def _openalex_work(cls, value: str) -> dict:
        doi = _doi(value)
        if _is_doi(doi):
            ident = f"https://doi.org/{doi}"
        elif value.startswith("https://openalex.org/") or re.match(r"^W\d+$", value.strip(), re.I):
            ident = value.strip()
            if ident.upper().startswith("W"):
                ident = "https://openalex.org/" + ident.upper()
        else:
            raise ValueError("需要 DOI 或 OpenAlex W-ID")
        return await _request_json(
            "GET",
            "https://api.openalex.org/works/" + quote(ident, safe=":/"),
            params=cls._oa_params(),
        )

    @staticmethod
    def _format_oa(item: dict, n: int | None = None) -> str:
        prefix = f"{n}. " if n is not None else ""
        title = item.get("display_name") or item.get("title") or "(untitled)"
        authors = _names_openalex(item.get("authorships") or [])
        year = item.get("publication_year") or "?"
        cited = item.get("cited_by_count", 0)
        doi = (item.get("doi") or "").replace("https://doi.org/", "")
        oa = "OA" if (item.get("open_access") or {}).get("is_oa") else "closed/unknown"
        line = f"{prefix}{title}\n   {authors or '作者未知'} · {year} · cited {cited} · {oa}"
        if doi:
            line += f" · DOI {doi}"
        return line

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> str:
        query = query.strip()
        if not query:
            raise ValueError("检索词不能为空")
        limit = max(1, min(int(limit), 10))
        data = await _request_json(
            "GET",
            "https://api.openalex.org/works",
            params=cls._oa_params({"search": query, "per-page": limit}),
        )
        rows = data.get("results", [])
        if not rows:
            return "OpenAlex 未找到论文"
        return "OpenAlex 文献检索\n" + "\n".join(cls._format_oa(x, i + 1) for i, x in enumerate(rows))

    @staticmethod
    async def lookup(value: str) -> str:
        value = value.strip()
        if _is_doi(value):
            doi = _doi(value)
            data = await _request_json("GET", f"https://api.crossref.org/works/{quote(doi, safe='')}")
            item = data.get("message", {})
        else:
            data = await _request_json(
                "GET",
                "https://api.crossref.org/works",
                params={"query.bibliographic": value, "rows": 1},
            )
            items = data.get("message", {}).get("items", [])
            if not items:
                return "Crossref 未找到结果"
            item = items[0]
        title = (item.get("title") or ["(untitled)"])[0]
        authors = _names_crossref(item.get("author") or [])
        published = (item.get("published-print") or item.get("published-online") or item.get("issued") or {}).get("date-parts", [["?"]])[0]
        year = published[0] if published else "?"
        venue = (item.get("container-title") or [""])[0]
        doi = item.get("DOI", "")
        cited = item.get("is-referenced-by-count", 0)
        typ = item.get("type", "")
        return f"{title}\n{authors or '作者未知'}\n{venue} · {year} · {typ} · cited {cited}\nDOI {doi}"

    @classmethod
    async def cited(cls, doi: str, limit: int = 5) -> str:
        work = await cls._openalex_work(doi)
        wid = work.get("id", "").rsplit("/", 1)[-1]
        data = await _request_json(
            "GET",
            "https://api.openalex.org/works",
            params=cls._oa_params({"filter": f"cites:{wid}", "per-page": max(1, min(limit, 10))}),
        )
        rows = data.get("results", [])
        if not rows:
            return "暂未查到引用该论文的工作"
        return "引用它的论文\n" + "\n".join(cls._format_oa(x, i + 1) for i, x in enumerate(rows))

    @classmethod
    async def references(cls, doi: str, limit: int = 5) -> str:
        work = await cls._openalex_work(doi)
        refs = (work.get("referenced_works") or [])[: max(1, min(limit, 8))]
        if not refs:
            return "OpenAlex 没有记录参考文献"
        rows = await asyncio.gather(*(cls._openalex_work(x) for x in refs), return_exceptions=True)
        items = [x for x in rows if isinstance(x, dict)]
        if not items:
            return "参考文献 ID 存在，但元数据读取失败"
        return "它引用的论文\n" + "\n".join(cls._format_oa(x, i + 1) for i, x in enumerate(items))

    @classmethod
    async def related(cls, doi: str, limit: int = 5) -> str:
        work = await cls._openalex_work(doi)
        ids = (work.get("related_works") or [])[: max(1, min(limit, 8))]
        if not ids:
            return "OpenAlex 暂无 related works"
        rows = await asyncio.gather(*(cls._openalex_work(x) for x in ids), return_exceptions=True)
        items = [x for x in rows if isinstance(x, dict)]
        return "相关论文\n" + "\n".join(cls._format_oa(x, i + 1) for i, x in enumerate(items))

    @classmethod
    async def oa(cls, doi: str) -> str:
        doi = _doi(doi)
        email = os.getenv("UNPAYWALL_EMAIL", "").strip()
        if email:
            try:
                up = await _request_json(
                    "GET",
                    f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                    params={"email": email},
                )
                loc = up.get("best_oa_location") or {}
                url = loc.get("url_for_pdf") or loc.get("url") or ""
                if url:
                    return f"Unpaywall: {'OA' if up.get('is_oa') else '非OA/未知'}\n{url}\nlicense: {loc.get('license') or 'unknown'}"
            except Exception:
                pass
        work = await cls._openalex_work(doi)
        oa = work.get("open_access") or {}
        loc = work.get("best_oa_location") or work.get("primary_location") or {}
        url = loc.get("pdf_url") or loc.get("landing_page_url") or oa.get("oa_url") or ""
        return f"OpenAlex: {'OA' if oa.get('is_oa') else '非OA/未知'} · {oa.get('oa_status') or 'unknown'}\n{url or '未找到合法开放全文地址'}"

    @staticmethod
    async def bib(doi: str, style: str = "bibtex") -> str:
        doi = _doi(doi)
        style = style.lower().strip()
        if style == "bibtex":
            accept = "application/x-bibtex"
        elif style == "ris":
            accept = "application/x-research-info-systems"
        elif style == "apa":
            accept = "text/x-bibliography; style=apa"
        elif style in {"gbt", "gb7714", "gbt7714"}:
            accept = "text/x-bibliography; style=chinese-gb7714-2005-numeric; locale=zh-CN"
        else:
            raise ValueError("style 支持 bibtex / ris / apa / gbt")
        return await _request_text(f"https://doi.org/{quote(doi, safe='/')}", headers={"Accept": accept})

    @classmethod
    async def check(cls, doi: str) -> str:
        doi = _doi(doi)
        cross = await _request_json("GET", f"https://api.crossref.org/works/{quote(doi, safe='')}")
        item = cross.get("message", {})
        updates = item.get("update-to") or []
        relations = item.get("relation") or {}
        try:
            oa = await cls._openalex_work(doi)
            retracted = bool(oa.get("is_retracted"))
        except Exception:
            retracted = False
        lines = [f"DOI {doi}", f"OpenAlex retracted: {'YES' if retracted else 'no'}"]
        if updates:
            lines.append("Crossref updates:")
            for x in updates[:8]:
                lines.append(f"- {x.get('type','update')}: {x.get('DOI','')} {x.get('label','')}")
        else:
            lines.append("Crossref update-to: none recorded")
        if relations:
            lines.append("Crossref relation fields: " + ", ".join(relations.keys()))
        lines.append("提示：未发现记录不等于论文绝对没有问题。")
        return "\n".join(lines)

    @staticmethod
    async def datasets(query: str, limit: int = 5) -> str:
        data = await _request_json(
            "GET",
            "https://api.datacite.org/dois",
            params={"query": query, "page[size]": max(1, min(limit, 10))},
        )
        rows = data.get("data", [])
        if not rows:
            return "DataCite 未找到研究输出"
        out = ["DataCite 数据/软件/研究输出"]
        for i, row in enumerate(rows, 1):
            a = row.get("attributes", {})
            title = ((a.get("titles") or [{}])[0]).get("title", "(untitled)")
            typ = (a.get("types") or {}).get("resourceTypeGeneral", "")
            out.append(f"{i}. {title}\n   {a.get('publicationYear','?')} · {typ} · DOI {a.get('doi','')}")
        return "\n".join(out)

    @staticmethod
    async def pubmed(query: str, limit: int = 5) -> str:
        data = await _request_json(
            "GET",
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": query, "pageSize": max(1, min(limit, 10)), "format": "json"},
        )
        rows = data.get("resultList", {}).get("result", [])
        if not rows:
            return "Europe PMC / PubMed 未找到结果"
        out = ["Europe PMC / PubMed"]
        for i, x in enumerate(rows, 1):
            ids = " · ".join(v for v in [f"PMID {x.get('pmid')}" if x.get("pmid") else "", f"PMCID {x.get('pmcid')}" if x.get("pmcid") else "", f"DOI {x.get('doi')}" if x.get("doi") else ""] if v)
            out.append(f"{i}. {x.get('title','(untitled)')}\n   {x.get('authorString','')} · {x.get('pubYear','?')} · {ids}")
        return "\n".join(out)

    @classmethod
    async def author(cls, query: str, limit: int = 5) -> str:
        data = await _request_json(
            "GET", "https://api.openalex.org/authors",
            params=cls._oa_params({"search": query, "per-page": max(1, min(limit, 10))}),
        )
        rows = data.get("results", [])
        if not rows:
            return "OpenAlex 未找到作者"
        out = ["OpenAlex authors"]
        for i, a in enumerate(rows, 1):
            stats = a.get("summary_stats") or {}
            aff = []
            for x in (a.get("affiliations") or [])[:3]:
                n = (x.get("institution") or {}).get("display_name")
                if n and n not in aff:
                    aff.append(n)
            out.append(f"{i}. {a.get('display_name')} · works {a.get('works_count',0)} · cited {a.get('cited_by_count',0)} · h {stats.get('h_index','?')}\n   {a.get('id','')} · ORCID {a.get('orcid') or 'n/a'} · {', '.join(aff)}")
        return "\n".join(out)

    @staticmethod
    async def organization(query: str, affiliation: bool = False, limit: int = 5) -> str:
        data = await _request_json("GET", "https://api.ror.org/v2/organizations", params={"affiliation" if affiliation else "query": query})
        rows = data.get("items", [])
        if not rows:
            return "ROR 未找到机构"
        out = ["ROR affiliation match" if affiliation else "ROR organizations"]
        for i, raw in enumerate(rows[:max(1, min(limit, 10))], 1):
            org = (raw.get("organization") if affiliation else raw) or {}
            names = org.get("names") or []
            display = next((n.get("value") for n in names if "ror_display" in (n.get("types") or [])), None)
            display = display or next((n.get("value") for n in names if n.get("value")), "(unknown)")
            loc = ((org.get("locations") or [{}])[0].get("geonames_details") or {})
            chosen = " · chosen" if affiliation and raw.get("chosen") else ""
            out.append(f"{i}. {display}{chosen} · {loc.get('country_name','')} {loc.get('name','')} · {org.get('id','')}")
        return "\n".join(out)

    @staticmethod
    async def arxiv(query: str, limit: int = 5) -> str:
        xml = await _request_text(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "start": 0, "max_results": max(1, min(limit, 10)), "sortBy": "relevance"},
            headers={"Accept": "application/atom+xml"},
            timeout=22,
        )
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml)
        entries = root.findall("a:entry", ns)
        if not entries:
            return "arXiv 未找到结果"
        out = ["arXiv"]
        for i, e in enumerate(entries, 1):
            title = _clean(e.findtext("a:title", default="", namespaces=ns), 300)
            aid = e.findtext("a:id", default="", namespaces=ns).rsplit("/", 1)[-1]
            authors = [a.findtext("a:name", default="", namespaces=ns) for a in e.findall("a:author", ns)]
            published = e.findtext("a:published", default="", namespaces=ns)[:10]
            out.append(f"{i}. {title}\n   {', '.join(authors[:5])}{' et al.' if len(authors)>5 else ''} · {published} · arXiv:{aid}")
        return "\n".join(out)


class BioService:
    MAP_ALIASES = {
        "uniprot": "UniProtKB_AC-ID",
        "uniprotkb": "UniProtKB_AC-ID",
        "pdb": "PDB",
        "geneid": "GeneID",
        "entrez": "GeneID",
        "ensembl": "Ensembl",
        "chembl": "ChEMBL",
        "drugbank": "DrugBank",
    }

    @staticmethod
    def _protein_line(x: dict) -> str:
        acc = x.get("primaryAccession", "")
        uid = x.get("uniProtkbId", "")
        desc = x.get("proteinDescription") or {}
        name = (((desc.get("recommendedName") or {}).get("fullName") or {}).get("value") or "")
        genes = x.get("genes") or []
        gene = (((genes[0].get("geneName") or {}).get("value")) if genes else "") or ""
        org = (x.get("organism") or {}).get("scientificName", "")
        length = (x.get("sequence") or {}).get("length", "?")
        return f"{acc} / {uid}\n{name}\ngene {gene} · {org} · {length} aa"

    @classmethod
    async def protein(cls, query: str) -> str:
        q = query.strip()
        looks_acc = bool(re.match(r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:[A-Z0-9]{3}[0-9])?)$", q, re.I))
        if looks_acc:
            data = await _request_json("GET", f"https://rest.uniprot.org/uniprotkb/{quote(q, safe='')}.json")
            return cls._protein_line(data)
        data = await _request_json(
            "GET",
            "https://rest.uniprot.org/uniprotkb/search",
            params={"query": f"({q}) AND (organism_id:9606)", "format": "json", "size": 3},
        )
        rows = data.get("results", [])
        if not rows:
            return "UniProt 未找到结果"
        return "UniProt\n" + "\n\n".join(cls._protein_line(x) for x in rows)

    @staticmethod
    async def domains(accession: str, limit: int = 8) -> str:
        data = await _request_json(
            "GET",
            f"https://www.ebi.ac.uk/interpro/api/entry/interpro/protein/uniprot/{quote(accession.strip(), safe='')}/",
            params={"page_size": max(1, min(limit, 20))},
        )
        rows = data.get("results", [])
        if not rows:
            return "InterPro 未找到结构域/家族注释"
        out = [f"InterPro · {accession}"]
        for x in rows[:limit]:
            m = x.get("metadata", {})
            out.append(f"- {m.get('accession','')} · {m.get('name','')} [{m.get('type','')}]")
        return "\n".join(out)

    @staticmethod
    async def gene(query: str, species: str = "homo_sapiens") -> str:
        q = query.strip()
        if re.match(r"^ENS[A-Z]*G\d+", q, re.I):
            url = f"https://rest.ensembl.org/lookup/id/{quote(q, safe='')}"
        else:
            url = f"https://rest.ensembl.org/lookup/symbol/{quote(species, safe='')}/{quote(q, safe='')}"
        x = await _request_json("GET", url, params={"expand": 1}, headers={"Content-Type": "application/json"})
        return (
            f"{x.get('display_name') or q} · {x.get('id','')}\n"
            f"{_clean(x.get('description',''), 400)}\n"
            f"{x.get('seq_region_name','?')}:{x.get('start','?')}-{x.get('end','?')} strand {x.get('strand','?')} · {x.get('biotype','')}"
        )

    @staticmethod
    async def pdb(pdb_id: str) -> str:
        x = await _request_json("GET", f"https://data.rcsb.org/rest/v1/core/entry/{quote(pdb_id.strip().upper(), safe='')}")
        title = (x.get("struct") or {}).get("title", "")
        methods = ", ".join(i.get("method", "") for i in (x.get("exptl") or []) if i.get("method"))
        info = x.get("rcsb_entry_info") or {}
        res = info.get("resolution_combined") or []
        res_text = f"{res[0]} Å" if res else "resolution n/a"
        return f"PDB {pdb_id.upper()}\n{title}\n{methods or 'method n/a'} · {res_text}"

    @staticmethod
    async def variant(variant_id: str) -> str:
        x = await _request_json(
            "GET",
            f"https://rest.ensembl.org/variation/human/{quote(variant_id.strip(), safe='')}",
            params={"phenotypes": 1, "pops": 1},
            headers={"Content-Type": "application/json"},
            timeout=25,
        )
        mappings = x.get("mappings") or []
        lines = [f"Ensembl variant {x.get('name') or variant_id}", f"most severe: {x.get('most_severe_consequence','unknown')}"]
        for m in mappings[:4]:
            lines.append(f"- {m.get('seq_region_name')}:{m.get('start')}-{m.get('end')} {m.get('allele_string','')} ({m.get('assembly_name','')})")
        phen = x.get("phenotypes") or []
        if phen:
            lines.append("phenotypes: " + "; ".join(_clean(p.get("trait", ""), 120) for p in phen[:5]))
        return "\n".join(lines)

    @staticmethod
    async def alphafold(accession: str) -> str:
        rows = await _request_json("GET", f"https://alphafold.ebi.ac.uk/api/prediction/{quote(accession.strip(), safe='')}")
        if not rows:
            return "AlphaFold DB 未找到预测"
        x = rows[0]
        return (
            f"AlphaFold {x.get('uniprotAccession') or accession} · {x.get('gene','')} · mean pLDDT {x.get('globalMetricValue','?')}\n"
            f"{x.get('uniprotDescription','')} · {x.get('organismScientificName','')}\n"
            f"PDB {x.get('pdbUrl','')}\nCIF {x.get('cifUrl','')}\nPAE {x.get('paeImageUrl','')}"
        )

    @staticmethod
    async def blast_submit(sequence: str) -> str:
        seq = re.sub(r"[^A-Za-z]", "", sequence).upper()
        if len(seq) < 8 or len(seq) > 10000:
            raise ValueError("BLAST 序列长度要求 8..10000；可直接粘贴 FASTA 序列内容")
        nucleotide = bool(re.fullmatch(r"[ACGTUN]+", seq))
        program = "blastn" if nucleotide else "blastp"
        database = "core_nt" if nucleotide else "swissprot"
        body = await _post_form_text(
            "https://blast.ncbi.nlm.nih.gov/Blast.cgi",
            {"CMD": "Put", "PROGRAM": program, "DATABASE": database, "QUERY": seq, "HITLIST_SIZE": 10},
            timeout=25,
        )
        rid = re.search(r"RID\s*=\s*([A-Z0-9-]+)", body)
        rtoe = re.search(r"RTOE\s*=\s*(\d+)", body)
        if not rid:
            raise AcademicError("NCBI BLAST 没有返回 RID")
        wait = rtoe.group(1) if rtoe else "若干"
        return f"NCBI {program} → {database}\nRID {rid.group(1)}\n预计 {wait} 秒后使用 /bio blastget {rid.group(1)}"

    @staticmethod
    async def blast_get(rid: str) -> str:
        text = await _request_text(
            "https://blast.ncbi.nlm.nih.gov/Blast.cgi",
            params={"CMD": "Get", "RID": rid.strip(), "FORMAT_TYPE": "Text", "DESCRIPTIONS": 8, "ALIGNMENTS": 5},
            timeout=25,
        )
        status = re.search(r"Status=(WAITING|FAILED|UNKNOWN|READY)", text)
        if status and status.group(1) == "WAITING":
            return f"BLAST {rid}: 仍在计算，稍后再 /bio blastget {rid}"
        if status and status.group(1) in {"FAILED", "UNKNOWN"}:
            return f"BLAST {rid}: {status.group(1)}"
        return text[:5000]

    @staticmethod
    async def pathway(query: str, limit: int = 6) -> str:
        x = await _request_json(
            "GET",
            "https://reactome.org/ContentService/search/query",
            params={"query": query, "species": "Homo sapiens", "types": "Pathway", "cluster": "true"},
        )
        entries = []
        for group in x.get("results", []):
            entries.extend(group.get("entries", []))
        if not entries:
            return "Reactome 未找到通路"
        out = ["Reactome pathways"]
        for e in entries[:limit]:
            out.append(f"- {e.get('stId') or e.get('id')} · {_clean(e.get('name',''), 180)}")
        return "\n".join(out)

    @staticmethod
    async def target(query: str) -> str:
        search_q = "query Q($q:String!){ search(queryString:$q){ hits { id name entity } } }"
        found = await _request_json(
            "POST",
            "https://api.platform.opentargets.org/api/v4/graphql",
            payload={"query": search_q, "variables": {"q": query}},
        )
        hits = ((found.get("data") or {}).get("search") or {}).get("hits") or []
        target = next((h for h in hits if h.get("entity") == "target"), None)
        if not target:
            return "Open Targets 未找到靶点"
        target_q = "query T($id:String!){ target(ensemblId:$id){ id approvedSymbol approvedName biotype tractability { label modality value } } }"
        data = await _request_json(
            "POST",
            "https://api.platform.opentargets.org/api/v4/graphql",
            payload={"query": target_q, "variables": {"id": target["id"]}},
        )
        t = (data.get("data") or {}).get("target") or {}
        tr = [f"{x.get('modality')}:{x.get('label')}" for x in (t.get("tractability") or []) if x.get("value")]
        return f"{t.get('approvedSymbol')} · {t.get('id')}\n{t.get('approvedName')} · {t.get('biotype')}\ntractability: {', '.join(tr[:12]) or 'none recorded'}"

    @classmethod
    async def map_ids(cls, source: str, target: str, ids: str) -> str:
        source = cls.MAP_ALIASES.get(source.lower(), source)
        target = cls.MAP_ALIASES.get(target.lower(), target)
        values = [x for x in re.split(r"[\s,;]+", ids.strip()) if x][:20]
        if not values:
            raise ValueError("至少提供一个 ID")
        job = await _request_json(
            "POST",
            "https://rest.uniprot.org/idmapping/run",
            form={"from": source, "to": target, "ids": ",".join(values)},
        )
        jid = job.get("jobId")
        if not jid:
            raise AcademicError("UniProt ID mapping 未返回 jobId")
        for _ in range(10):
            status = await _request_json("GET", f"https://rest.uniprot.org/idmapping/status/{jid}")
            if status.get("jobStatus") == "RUNNING":
                await asyncio.sleep(0.5)
                continue
            break
        result = await _request_json(
            "GET",
            f"https://rest.uniprot.org/idmapping/results/{jid}",
            params={"format": "json", "size": 50},
        )
        rows = result.get("results", [])
        failed = result.get("failedIds", [])
        out = [f"UniProt ID mapping · {source} → {target}"]
        for x in rows[:30]:
            to = x.get("to")
            if isinstance(to, dict):
                to = to.get("primaryAccession") or to.get("uniProtkbId") or to.get("id") or json.dumps(to, ensure_ascii=False)[:180]
            out.append(f"{x.get('from')} → {to}")
        if failed:
            out.append("failed: " + ", ".join(map(str, failed[:20])))
        return "\n".join(out)


class ResearchChemService:
    @staticmethod
    async def info(compound: str) -> str:
        x = await _request_json(
            "GET",
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote(compound.strip(), safe='')}/property/Title,MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,InChIKey/JSON",
        )
        rows = (x.get("PropertyTable") or {}).get("Properties") or []
        if not rows:
            return "PubChem 未找到化合物"
        p = rows[0]
        smiles = p.get("ConnectivitySMILES") or p.get("CanonicalSMILES") or p.get("SMILES") or ""
        return f"PubChem CID {p.get('CID')} · {p.get('Title') or compound}\n{p.get('MolecularFormula')} · MW {p.get('MolecularWeight')}\nSMILES {smiles}\nInChIKey {p.get('InChIKey','')}"

    @staticmethod
    async def drug(query: str) -> str:
        x = await _request_json(
            "GET",
            "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json",
            params={"q": query, "limit": 3},
        )
        rows = x.get("molecules", [])
        if not rows:
            return "ChEMBL 未找到分子"
        m = rows[0]
        cid = m.get("molecule_chembl_id", "")
        mech = await _request_json(
            "GET",
            "https://www.ebi.ac.uk/chembl/api/data/mechanism.json",
            params={"molecule_chembl_id": cid, "limit": 8},
        )
        props = m.get("molecule_properties") or {}
        out = [f"{m.get('pref_name') or query} · {cid} · max phase {m.get('max_phase','?')} · MW {props.get('full_mwt','?')}"]
        for row in (mech.get("mechanisms") or [])[:8]:
            out.append(f"- {row.get('mechanism_of_action') or row.get('action_type') or 'mechanism'} · {row.get('target_chembl_id','')} {row.get('target_name','')}")
        return "\n".join(out)

    @staticmethod
    async def target(query: str) -> str:
        x = await _request_json(
            "GET",
            "https://www.ebi.ac.uk/chembl/api/data/target/search.json",
            params={"q": query, "limit": 5},
        )
        rows = x.get("targets", [])
        if not rows:
            return "ChEMBL 未找到 target"
        out = ["ChEMBL targets"]
        for t in rows[:5]:
            out.append(f"- {t.get('target_chembl_id')} · {t.get('pref_name')} · {t.get('target_type')} · {t.get('organism','')}")
        return "\n".join(out)


class MaterialService:
    DEFAULT = "https://optimade.materialscloud.org/main/mc3d-pbe-v1/v1/structures"

    @staticmethod
    async def providers(limit: int = 30) -> str:
        x = await _request_json("GET", "https://providers.optimade.org/v1/links")
        rows = x.get("data", [])
        out = ["OPTIMADE providers"]
        for r in rows[: max(1, min(limit, 50))]:
            a = r.get("attributes", {})
            out.append(f"- {r.get('id')} · {a.get('name')} · {a.get('homepage') or a.get('base_url') or ''}")
        return "\n".join(out)

    @staticmethod
    def _formula_filter(value: str) -> str:
        elements = re.findall(r"[A-Z][a-z]?", value)
        unique = []
        for e in elements:
            if e not in unique:
                unique.append(e)
        if not unique:
            raise ValueError("无法从输入识别元素；也可以直接写 filter:<OPTIMADE filter>")
        quoted = ", ".join(f'"{e}"' for e in unique)
        return f"elements HAS ALL {quoted} AND nelements={len(unique)}"

    @classmethod
    async def find(cls, query: str, limit: int = 5) -> str:
        q = query.strip()
        filt = q[7:].strip() if q.lower().startswith("filter:") else cls._formula_filter(q)
        data = await _request_json(
            "GET",
            cls.DEFAULT,
            params={"filter": filt, "page_limit": max(1, min(limit, 10)), "response_fields": "chemical_formula_reduced,elements,nelements,lattice_vectors,nsites"},
        )
        rows = data.get("data", [])
        if not rows:
            return f"Materials Cloud/OPTIMADE 未找到结果\nfilter: {filt}"
        out = [f"Materials Cloud · OPTIMADE\nfilter: {filt}"]
        for i, r in enumerate(rows, 1):
            a = r.get("attributes", {})
            out.append(f"{i}. {a.get('chemical_formula_reduced','?')} · {a.get('nsites','?')} sites · id {r.get('id')}")
        return "\n".join(out)


class AstroService:
    @staticmethod
    def _tap_rows(x: dict) -> list[dict]:
        names = [m.get("name") for m in x.get("metadata", [])]
        return [dict(zip(names, row)) for row in x.get("data", [])]

    @classmethod
    async def object(cls, identifier: str) -> str:
        ident = identifier.strip().replace("'", "''")
        query = f"SELECT TOP 5 b.main_id,b.ra,b.dec,b.otype FROM basic AS b JOIN ident AS i ON b.oid=i.oidref WHERE i.id='{ident}'"
        x = await _request_json(
            "GET",
            "https://simbad.cds.unistra.fr/simbad/sim-tap/sync",
            params={"request": "doQuery", "lang": "adql", "format": "json", "query": query},
        )
        rows = cls._tap_rows(x)
        if not rows:
            return "SIMBAD 未找到对象；请尝试标准天体标识，例如 M 31 / Betelgeuse"
        out = ["SIMBAD"]
        for r in rows:
            out.append(f"- {r.get('main_id')} · {r.get('otype')} · RA {r.get('ra')}° · Dec {r.get('dec')}°")
        return "\n".join(out)

    @staticmethod
    async def exoplanet(name: str, limit: int = 5) -> str:
        n = name.strip().replace("'", "''").lower()
        q = (
            "SELECT TOP %d pl_name,hostname,disc_year,pl_rade,pl_bmasse,pl_orbper,st_teff "
            "FROM pscomppars WHERE lower(pl_name) like '%%%s%%' OR lower(hostname) like '%%%s%%'"
        ) % (max(1, min(limit, 10)), n, n)
        rows = await _request_json(
            "GET",
            "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
            params={"query": q, "format": "json"},
        )
        if not rows:
            return "NASA Exoplanet Archive 未找到结果"
        out = ["NASA Exoplanet Archive"]
        for r in rows:
            out.append(f"- {r.get('pl_name')} · host {r.get('hostname')} · {r.get('disc_year')} · R {r.get('pl_rade')} R⊕ · M {r.get('pl_bmasse')} M⊕ · P {r.get('pl_orbper')} d")
        return "\n".join(out)

    @staticmethod
    async def ads(query: str, limit: int = 5) -> str:
        token = os.getenv("NASA_ADS_TOKEN", "").strip() or os.getenv("ADS_API_TOKEN", "").strip()
        if not token:
            return "NASA ADS 需要配置 NASA_ADS_TOKEN；当前未配置。可先用 /paper search。"
        x = await _request_json(
            "GET",
            "https://api.adsabs.harvard.edu/v1/search/query",
            params={"q": query, "fl": "bibcode,title,author,year,citation_count,doi", "rows": max(1, min(limit, 10))},
            headers={"Authorization": f"Bearer {token}"},
        )
        docs = (x.get("response") or {}).get("docs") or []
        if not docs:
            return "ADS 未找到结果"
        out = ["NASA ADS"]
        for i, d in enumerate(docs, 1):
            title = (d.get("title") or ["(untitled)"])[0]
            out.append(f"{i}. {title}\n   {', '.join((d.get('author') or [])[:4])} · {d.get('year','?')} · cited {d.get('citation_count',0)} · {d.get('bibcode','')}")
        return "\n".join(out)


class TrialService:
    @staticmethod
    def _line(study: dict) -> str:
        p = study.get("protocolSection") or {}
        ident = p.get("identificationModule") or {}
        status = p.get("statusModule") or {}
        design = p.get("designModule") or {}
        nct = ident.get("nctId", "")
        title = ident.get("briefTitle") or ident.get("officialTitle") or "(untitled)"
        phases = ",".join(design.get("phases") or [])
        return f"{nct} · {status.get('overallStatus','')} · {phases}\n{title}"

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> str:
        x = await _request_json(
            "GET",
            "https://clinicaltrials.gov/api/v2/studies",
            params={"query.term": query, "pageSize": max(1, min(limit, 10)), "format": "json"},
        )
        rows = x.get("studies", [])
        if not rows:
            return "ClinicalTrials.gov 未找到试验"
        return "ClinicalTrials.gov\n" + "\n\n".join(cls._line(s) for s in rows)

    @classmethod
    async def get(cls, nct_id: str) -> str:
        s = await _request_json("GET", f"https://clinicaltrials.gov/api/v2/studies/{quote(nct_id.strip().upper(), safe='')}")
        p = s.get("protocolSection") or {}
        ident = p.get("identificationModule") or {}
        status = p.get("statusModule") or {}
        cond = p.get("conditionsModule") or {}
        design = p.get("designModule") or {}
        desc = p.get("descriptionModule") or {}
        contacts = p.get("contactsLocationsModule") or {}
        lines = [cls._line(s)]
        lines.append("conditions: " + ", ".join(cond.get("conditions") or []))
        lines.append(f"enrollment: {(design.get('enrollmentInfo') or {}).get('count','?')}")
        if status.get("startDateStruct"):
            lines.append("start: " + str((status.get("startDateStruct") or {}).get("date", "")))
        sponsor = (p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
        if sponsor:
            lines.append("sponsor: " + sponsor.get("name", ""))
        if desc.get("briefSummary"):
            lines.append(_clean(desc.get("briefSummary"), 800))
        return "\n".join(lines)
