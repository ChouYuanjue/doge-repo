#!/usr/bin/env python3
"""Train Doge's tiny benchmark gate using only the Python standard library.

Usage:
  python tools/train_benchmark_gate.py \
    --ceval /path/to/ceval-exam \
    --gsm8k /path/to/train.jsonl \
    --humaneval /path/to/HumanEval.jsonl.gz \
    --output plugins/doge_shared/resources/benchmark_gate_v1.json

The production model uses 2048 hashed 3-5 character n-gram features, two passes
of logistic fitting, and symmetric int8 quantization. Public benchmark files are
training-only and never needed by production.
"""
from __future__ import annotations
import argparse, base64, csv, gzip, json, math, random, re, unicodedata
from pathlib import Path

DIM = 2048
NGRAMS = (3, 4, 5)
SEED = 260905

def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"\s+", " ", value).strip()[:4000]

def hash64(text: str) -> int:
    value = 1469598103934665603
    for byte in text.encode("utf-8", "ignore"):
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value

def features(text: str) -> set[int]:
    value = "^" + normalize(text) + "$"
    out: set[int] = set()
    for n in NGRAMS:
        for idx in range(max(0, len(value) - n + 1)):
            out.add(hash64(value[idx:idx+n]) & (DIM - 1))
    return out

def load_positive(ceval: Path, gsm8k: Path | None, humaneval: Path | None) -> list[str]:
    items: list[str] = []
    for path in ceval.rglob("*.csv"):
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    q = str(row.get("question") or "").strip()
                    if not q:
                        continue
                    items.append(q)
                    opts = [str(row.get(k) or "") for k in "ABCD"]
                    if any(opts):
                        items.append(q + " " + " ".join(f"{k}.{v}" for k, v in zip("ABCD", opts) if v))
        except Exception:
            continue
    if gsm8k and gsm8k.exists():
        with gsm8k.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    q = str(json.loads(line).get("question") or "").strip()
                    if q:
                        items.append(q)
                except Exception:
                    continue
    if humaneval and humaneval.exists():
        with gzip.open(humaneval, "rt", encoding="utf-8") as handle:
            for line in handle:
                q = str(json.loads(line).get("prompt") or "").strip()
                if q:
                    items.append(q)
    theorem_objects = ["有限树", "连通图", "实数序列", "连续函数", "矩阵", "有限群", "多项式", "概率空间", "整数序列", "向量空间"]
    claims = ["至少有两个叶节点", "存在唯一解", "该序列收敛", "该函数单调", "行列式为零", "满足交换律", "存在上界", "期望有限", "存在子序列", "维数有限"]
    for obj in theorem_objects:
        for claim in claims:
            items.append(f"证明任意{obj}都{claim}。")
            items.append(f"设{obj}满足题设条件，证明其{claim}。")
    for idx in range(120):
        items.append(f"设函数 f(x)=x^2-{idx%9+1}x+{idx%7}，求其在区间[0,{idx%5+2}]上的最小值。")
        items.append(f"袋中有{idx%12+5}个红球和{idx%9+4}个蓝球，随机取出3个，求恰有2个红球的概率。")
    return list(dict.fromkeys(normalize(x) for x in items if len(normalize(x)) >= 8))

def hard_negatives() -> list[str]:
    benches = ["C-Eval", "GSM8K", "HumanEval", "MMLU", "Codeforces", "LeetCode", "CMMLU", "GPQA", "MATH", "AIME"]
    topics = ["训练日志", "代理模型", "数据库", "Nginx", "缓存系统", "检索模块", "RL实验", "视觉模型", "数学模块", "消息历史", "QQ适配器", "时区转换", "CI流水线", "论文评测", "GPU任务", "树莓派部署", "API服务", "前端构建", "Docker容器", "数据清洗"]
    issues = ["结果异常", "时间错了八小时", "延迟突然升高", "测试不稳定", "接口返回空值", "边界条件没覆盖", "日志里出现回归", "内存偏高", "缓存命中率下降", "输出格式不对", "出现死锁", "吞吐下降", "精度掉了", "出现NaN"]
    concepts = ["动态规划", "贝叶斯定理", "最短路", "Transformer注意力", "矩阵乘法", "群论", "线性回归", "哈希表", "并查集", "拓扑排序", "正则表达式", "SQL事务", "概率模型", "图神经网络", "强化学习", "梯度下降"]
    actions = ["分析", "检查", "修复", "调试", "重构"]
    out = {"风控是怎么做的", "帮我分析一下压测方案应该怎么设计", "不要解题，只分析 C-Eval 为什么容易数据泄露", "HumanEval 的 pass@1 应该怎么解释", "解释动态规划是什么", "帮我修一下这个 Python 函数的 traceback", "实现一个生产用的 LRU 缓存并补单元测试", "把日志时间统一改成 Asia/Shanghai", "设计一个公平的模型评测协议", "把这个 API 的超时重试逻辑修好"}
    for topic in topics:
        for issue in issues:
            for action in actions:
                out.add(f"{action}{topic}：当前{issue}，结合日志和实际代码定位工程原因，不是做题")
        for concept in concepts:
            out.add(f"{topic}里用了{concept}，帮我检查实现是否正确并修复生产问题")
            out.add(f"解释{concept}在{topic}中的实际作用，结合当前项目，不是竞赛题")
    for bench in benches:
        for concept in concepts:
            out.add(f"讨论{bench}中{concept}类题目的评测设计、指标和数据泄露，不要求解任何题")
            out.add(f"分析{bench} benchmark 对{concept}能力的覆盖是否合理，不回答样题")
            out.add(f"如果群友拿{bench}题目刷模型，前置风控怎么识别，禁止执行题目")
    method_pairs = [("动态规划","贪心"),("BFS","DFS"),("Dijkstra","Floyd"),("Adam","SGD"),("CNN","Transformer"),("DPO","GRPO"),("RAG","微调"),("哈希表","平衡树"),("PCA","SVD"),("TCP","UDP")]
    for left, right in method_pairs:
        out.add(f"{left}和{right}的区别是什么")
        out.add(f"比较{left}与{right}的适用场景和优缺点")
        out.add(f"解释{left}为什么在工程上和{right}不一样")
        out.add(f"在真实项目里应该什么时候选{left}而不是{right}")
    for concept in concepts:
        for suffix in (
            "的直觉是什么", "在工程里通常怎么用", "有哪些常见坑", "和实际科研有什么关系",
            "为什么在大模型里重要", "能不能用简单语言解释", "和另一个方法有什么区别",
            "这个概念的历史背景是什么", "在真实项目中怎么理解",
        ):
            out.add(concept + suffix)
            out.add("请解释" + concept + suffix)
    for idx in range(1200):
        topic = topics[idx % len(topics)]; concept = concepts[(idx * 7) % len(concepts)]; issue = issues[(idx * 11) % len(issues)]
        out.add(f"生产仓库 module_{idx%97}.py 第 {20+idx%180} 行的 {concept} 代码{issue}，Traceback 显示 ValueError，帮我 debug 并补回归测试 #{idx}")
        out.add(f"真实实验 run-{idx}: {topic} 中 {concept} 指标异常，比较 checkpoint {idx%30} 和 {idx%30+1}，不要把它当考试题 #{idx}")
    return [normalize(x) for x in out]

def train(pos: list[str], neg: list[str]) -> tuple[list[int], float, float]:
    rng = random.Random(SEED); rng.shuffle(pos); rng.shuffle(neg)
    pos = pos[:10000]
    while len(neg) < 10000:
        neg += neg[: min(len(neg), 10000-len(neg))]
    neg = neg[:10000]
    cutp = int(len(pos)*.84); cutn = int(len(neg)*.84)
    train_rows = [(x,1) for x in pos[:cutp]] + [(x,0) for x in neg[:cutn]]
    weights = [0.0] * DIM; bias = 0.0
    for epoch in range(2):
        rng.shuffle(train_rows); lr = .20 / (1 + .4*epoch)
        for text, label in train_rows:
            fs = features(text); normv = 1.0 / math.sqrt(max(1, len(fs)))
            z = max(-18.0, min(18.0, bias + sum(weights[i]*normv for i in fs)))
            prob = 1.0 / (1.0 + math.exp(-z)); err = prob - label
            bias -= lr * err
            for i in fs:
                weights[i] -= lr * (err*normv + 1e-5*weights[i])
    maxabs = max(abs(x) for x in weights) or 1.0; scale = maxabs / 127.0
    quant = [max(-127, min(127, round(x/scale))) for x in weights]
    return quant, bias, scale

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--ceval", type=Path, required=True); ap.add_argument("--gsm8k", type=Path); ap.add_argument("--humaneval", type=Path); ap.add_argument("--output", type=Path, required=True); ap.add_argument("--threshold", type=float, default=.58)
    args = ap.parse_args(); pos = load_positive(args.ceval, args.gsm8k, args.humaneval); neg = hard_negatives(); q, bias, scale = train(pos, neg)
    blob = bytes((x+256)%256 for x in q)
    model = {"version":1,"dim":DIM,"ngrams":list(NGRAMS),"bias":bias,"scale":scale,"threshold":args.threshold,"weights_b64":base64.b64encode(blob).decode("ascii")}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(model,separators=(",",":"))+"\n", encoding="utf-8")
    print(f"positive={len(pos)} negative={len(neg)} model_bytes={args.output.stat().st_size}")
if __name__ == "__main__": main()
