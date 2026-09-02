from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


class LifeSessionStore:
    """Small durable store for the exact final Life board per AstrBot session."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, session_key: str) -> Path:
        key = hashlib.sha256(str(session_key).encode("utf-8", "ignore")).hexdigest()[:24]
        return self.root / f"{key}.npz"

    def save(self, session_key: str, board: np.ndarray, *, rule: str, boundary: str, label: str, generation: int) -> None:
        path = self.path_for(session_key); path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as fh:
            np.savez_compressed(
                fh,
                board=np.asarray(board, dtype=np.uint8),
                rule=np.array(str(rule)),
                boundary=np.array(str(boundary)),
                label=np.array(str(label)),
                generation=np.array(int(generation), dtype=np.int64),
            )
        tmp.replace(path)

    def load(self, session_key: str) -> dict | None:
        path = self.path_for(session_key)
        if not path.is_file():
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                board = np.asarray(data["board"], dtype=bool)
                if board.ndim != 2 or board.shape[0] != board.shape[1]:
                    raise ValueError("Life state board must be square")
                return {
                    "board": board,
                    "rule": str(data["rule"].item()),
                    "boundary": str(data["boundary"].item()),
                    "label": str(data["label"].item()),
                    "generation": int(data["generation"].item()),
                }
        except Exception:
            path.unlink(missing_ok=True)
            return None

    def clear(self, session_key: str) -> bool:
        path = self.path_for(session_key)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed
