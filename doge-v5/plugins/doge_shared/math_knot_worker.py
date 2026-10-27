"""Short-lived KnotPy worker: computes invariants from verified named/PD input.

This process has resource limits; never imports or evaluates user Python code.
"""
from __future__ import annotations

import json
import re
import sys
import resource


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (6, 7))
    resource.setrlimit(resource.RLIMIT_AS, (420 * 1024 * 1024, 420 * 1024 * 1024))
    raw=sys.stdin.read(1800)
    req=json.loads(raw)
    name=str(req["source"]).strip()
    kind=str(req.get("kind","name"))
    poly=str(req.get("poly","all")).lower()
    if poly not in {"all","alexander","jones","det"}:
        raise ValueError("poly 需为 all / alexander / jones / det")
    if kind=="name":
        if not re.fullmatch(r"(?:[+-]?[1-9][0-9]?_[1-9][0-9]{0,2}|unknot)",name) or len(name)>16:
            raise ValueError("结名需为 3_1、4_1、7_2 等格式")
    elif kind=="pd":
        if not 8<=len(name)<=750 or not re.fullmatch(r"[\d\s,\[\]XPD]+",name):
            raise ValueError("PD 格式需为 [[1,5,2,4],...] 或 PD[X[1,5,2,4],...]")
        if name.count("[")>40:
            raise ValueError("PD 输入过大")
    else:raise ValueError("仅支持 name 或 pd 表示")

    import knotpy as kp
    import sympy as sp
    if kind=="name": k=kp.knot(name)
    else: k=kp.from_pd_notation(name)
    crossings=len(k.crossings)
    if crossings>10:raise ValueError("目前每次计算最多 10 个交叉；更复杂结需单独离线计算")
    try:
        components=kp.number_of_link_components(k)
    except Exception:
        components=None
    answer={"input":name, "crossings":crossings, "components":components,
            "library":"KnotPy (BSD-3-Clause; b5fcf1a)"}
    # Alexander/Jones outputs are symbolic invariants of the supplied diagram,
    # not classifications.  Distinct knots can share the same polynomials.
    if poly in {"all","alexander","det"}:
        alex=sp.cancel(kp.alexander(k))
        answer["alexander"]=str(alex)
        if poly in {"all","det"}:
            answer["determinant"]=str(sp.simplify(abs(alex.subs(sp.Symbol("t"),-1))))
    if poly in {"all","jones"}:
        answer["jones"]=str(sp.cancel(kp.jones(k)))
    print(json.dumps(answer,ensure_ascii=False))


if __name__=="__main__":
    try:main()
    except Exception as e:
        print(json.dumps({"error":str(e)[:350]},ensure_ascii=False))
        sys.exit(1)
