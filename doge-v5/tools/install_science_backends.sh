#!/bin/sh
# Reproduce deployed, bounded /math knot + /lab FEM backends on server10.
# Run on server10 after setting up the official AstrBot Python runtime.
set -eu

UV="${UV:-/root/.local/bin/uv}"
PYTHON="${ASTRBOT_PYTHON:-/root/.local/share/uv/tools/astrbot/bin/python}"
KNOT_DIR="${DOGE_KNOTPY_DIR:-/opt/doge-science/knotpy}"
SHA="b5fcf1a"
REPO="https://github.com/bgabrovsek/knotpy.git"

test -x "$UV" || { echo "missing uv binary" >&2; exit 1; }
test -x "$PYTHON" || { echo "missing AstrBot Python" >&2; exit 1; }
command -v bwrap >/dev/null || { echo "missing required bubblewrap sandbox" >&2; exit 1; }

# The earlier research-only pyknotid package is NOT a runtime dependency.
"$UV" pip install --python "$PYTHON" 'scikit-fem==12.0.2' 'tqdm==4.70.1'

if [ ! -d "$KNOT_DIR/.git" ]; then
    mkdir -p "$(dirname "$KNOT_DIR")"
    git clone --filter=blob:none --depth=1 "$REPO" "$KNOT_DIR"
fi

current="$(git -C "$KNOT_DIR" rev-parse --short=7 HEAD)"
if [ "$current" != "$SHA" ]; then
    git -C "$KNOT_DIR" fetch --depth=1 origin "$SHA"
    git -C "$KNOT_DIR" checkout --detach "$SHA"
fi

# One minimal upstream typo at pinned revision; keep diff explicit.
draw="$KNOT_DIR/knotpy/drawing/draw.py"
if grep -q '^from classes.node import crossing$' "$draw"; then
    sed -i 's/^from classes.node import crossing$/from knotpy.classes.node import Crossing as crossing/' "$draw"
elif ! grep -q '^from knotpy.classes.node import Crossing as crossing$' "$draw"; then
    echo "Unexpected upstream KnotPy draw.py; refusing to guess a patch" >&2
    exit 1
fi

PYTHONPATH="$KNOT_DIR" OPENBLAS_NUM_THREADS=1 "$PYTHON" - <<'PY'
from skfem import MeshTri, ElementTriMorley
import knotpy as kp
from sympy import Symbol
k3 = kp.knot("3_1")
k4 = kp.knot("4_1")
t = Symbol("t")
assert abs(int(kp.alexander(k3).subs(t,-1))) == 3
assert abs(int(kp.alexander(k4).subs(t,-1))) == 5
print("OK: scikit-fem 12.0.2, pinned KnotPy b5fcf1a, verified Alexander invariants")
PY

echo "Standalone libraries ready. Restart doge-astrbot.service after deploying matching plugin sources."
