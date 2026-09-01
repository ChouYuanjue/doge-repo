from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from PIL import Image
from doge_code.executor import RunoobExecutor
from doge_media.media_service import trace_image
from doge_shared.academic import AstroService, BioService, MaterialService, PaperService, ResearchChemService, TrialService
from doge_shared.lookup import LookupService
from doge_shared.services import BingService, NasaService
from doge_shared.weather import WeatherService


async def check(name: str, awaitable, predicate=lambda x: bool(x)) -> dict:
    start = time.perf_counter()
    try:
        value = await awaitable
        ok = bool(predicate(value))
        return {"name": name, "ok": ok, "seconds": round(time.perf_counter() - start, 3), "sample": str(value)[:240]}
    except Exception as exc:
        return {"name": name, "ok": False, "seconds": round(time.perf_counter() - start, 3), "error": f"{type(exc).__name__}: {exc}"}


async def main(strict: bool) -> int:
    results = []
    results.append(await check("paper.lookup", PaperService.lookup("10.48550/arXiv.1706.03762"), lambda x: "2017" in x and "DataCite" in x))
    results.append(await check("bio.protein", BioService.protein("P69905"), lambda x: "Hemoglobin" in x))
    results.append(await check("chem.pubchem", ResearchChemService.info("aspirin"), lambda x: "PubChem" in x and "2244" in x))
    results.append(await check("chem.drug", ResearchChemService.drug("imatinib"), lambda x: "CHEMBL941" in x))
    results.append(await check("materials.optimade", MaterialService.providers(20), lambda x: "OPTIMADE" in x and "Example provider" not in x))
    results.append(await check("astro.simbad", AstroService.object("M 31"), lambda x: "SIMBAD" in x))
    results.append(await check("clinical", TrialService.search("glioblastoma", 1), lambda x: "ClinicalTrials.gov" in x))
    results.append(await check("lookup", LookupService.auto("图灵", "zh"), lambda x: "Wikidata" in x))
    results.append(await check("weather", WeatherService.forecast("Nanjing", 1), lambda x: isinstance(x, dict) and bool(x.get("current"))))
    results.append(await check("nasa.apod", NasaService.apod(), lambda x: isinstance(x, dict) and str(x.get("source", "")).startswith("NASA")))
    results.append(await check("bing", BingService.today(), lambda x: isinstance(x, dict) and str(x.get("url", "")).startswith("http")))
    results.append(await check("run.python", RunoobExecutor().execute("python", "print(6*7)"), lambda x: x.strip() == "42"))
    with tempfile.TemporaryDirectory() as td:
        image = Path(td) / "synthetic.png"
        Image.new("RGB", (64, 64), "white").save(image)
        # A synthetic image is expected to have no match; the audit only asserts
        # that the real AnimeTrace protocol round-trip completes normally.
        results.append(await check("media.animetrace", trace_image(image, "anime"), lambda x: isinstance(x, str) and bool(x.strip())))
    print(json.dumps({"ok": all(x["ok"] for x in results), "results": results}, ensure_ascii=False, indent=2))
    return 0 if (all(x["ok"] for x in results) or not strict) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.strict)))
