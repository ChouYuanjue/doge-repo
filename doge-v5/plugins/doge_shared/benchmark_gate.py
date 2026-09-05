from __future__ import annotations

import base64
import json
import math
import re
import unicodedata
from pathlib import Path

# Clear evidence that a request is about real engineering/research work or about
# the evaluation/security mechanism itself. This bypass happens before the tiny
# statistical detector; explicit benchmark-shaped problems are still caught by
# the high-precision gate in persona_runtime before this module is consulted.
_REAL_WORK_CONTEXT = re.compile(
    r"(?:生产|线上|仓库|服务|接口|api\b|日志|traceback|exception|报错|bug\b|debug|调试|修复|回归测试|部署|ci\b|checkpoint|"
    r"真实实验|实验结果|论文|数据泄露|评测脚本|超时|重试|"
    r"(?:评审|审查|review).{0,30}(?:项目|工程|课设|架构|代码|模块)|"
    r"(?:项目|工程|课设|架构|代码|模块).{0,30}(?:评审|审查|review)|"
    r"(?:风控|门控).{0,16}(?:怎么|如何|设计|机制|原理|有意思|听说|实现|比较)|"
    r"benchmark.{0,12}(?:设计|指标|口径|风控|泄露|脚本|框架)|(?:设计|分析|比较).{0,12}benchmark)",
    re.I,
)


def clear_real_work_context(text: str) -> bool:
    return bool(_REAL_WORK_CONTEXT.search(str(text or "")))


class TinyBenchmarkGate:
    """Dependency-free int8 hashed character n-gram benchmark detector.

    Runtime footprint is a 2048-byte weight vector plus a few scalar values.
    It is intentionally a supplement to deterministic high-precision rules,
    not a replacement for them.
    """

    def __init__(self, model_path: Path | None = None):
        path = model_path or Path(__file__).with_name("resources") / "benchmark_gate_v1.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.dim = int(raw["dim"])
        if self.dim <= 0 or self.dim & (self.dim - 1):
            raise ValueError("benchmark gate dim must be a power of two")
        self.ngrams = tuple(int(x) for x in raw["ngrams"])
        self.bias = float(raw["bias"])
        self.scale = float(raw["scale"])
        self.threshold = float(raw["threshold"])
        blob = base64.b64decode(raw["weights_b64"])
        if len(blob) != self.dim:
            raise ValueError("benchmark gate weight length mismatch")
        self.weights = tuple(b if b < 128 else b - 256 for b in blob)

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFKC", str(text or "")).lower()
        return re.sub(r"\s+", " ", value).strip()[:4000]

    @staticmethod
    def _hash64(text: str) -> int:
        value = 1469598103934665603
        for byte in text.encode("utf-8", "ignore"):
            value ^= byte
            value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
        return value

    def _features(self, text: str) -> set[int]:
        value = "^" + self._normalize(text) + "$"
        mask = self.dim - 1
        out: set[int] = set()
        for n in self.ngrams:
            for idx in range(max(0, len(value) - n + 1)):
                out.add(self._hash64(value[idx : idx + n]) & mask)
        return out

    def score(self, text: str) -> float:
        features = self._features(text)
        if not features:
            return float("-inf")
        norm = 1.0 / math.sqrt(len(features))
        return self.bias + sum(self.weights[i] * self.scale * norm for i in features)

    def is_benchmark(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value or clear_real_work_context(value):
            return False
        return self.score(value) >= self.threshold


GATE = TinyBenchmarkGate()
