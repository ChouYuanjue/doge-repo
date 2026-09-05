from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
if str(PLUGINS) not in sys.path:
    sys.path.insert(0, str(PLUGINS))

from doge_shared.parallel_agent import _ParallelExecutionLockManager, merge_parallel_history


class ParallelAgentTests(unittest.TestCase):
    def test_same_session_execution_lock_is_non_blocking(self):
        async def run():
            manager = _ParallelExecutionLockManager()
            both_inside = asyncio.Event()
            count = 0
            guard = asyncio.Lock()

            async def worker():
                nonlocal count
                async with manager.acquire_lock("same-session"):
                    async with guard:
                        count += 1
                        if count == 2:
                            both_inside.set()
                    await asyncio.wait_for(both_inside.wait(), timeout=0.3)

            await asyncio.wait_for(asyncio.gather(worker(), worker()), timeout=0.5)
            return count

        self.assertEqual(asyncio.run(run()), 2)

    def test_parallel_runs_append_both_tails(self):
        h = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "old-a"}]
        a = [{"role": "user", "content": "A"}, {"role": "assistant", "content": "answer-A"}]
        b = [{"role": "user", "content": "B"}, {"role": "assistant", "content": "answer-B"}]

        current, mode_b = merge_parallel_history(h, h, h + b)
        final, mode_a = merge_parallel_history(h, current, h + a)
        self.assertEqual(mode_b, "append-tail")
        self.assertEqual(mode_a, "append-tail")
        self.assertEqual(final, h + b + a)
        self.assertIn(a[0], final)
        self.assertIn(b[0], final)

    def test_repeated_save_is_idempotent(self):
        h = [{"role": "user", "content": "old"}]
        tail = [{"role": "user", "content": "A"}, {"role": "assistant", "content": "answer"}]
        current, _ = merge_parallel_history(h, h, h + tail)
        again, mode = merge_parallel_history(h, current, h + tail)
        self.assertEqual(again, current)
        self.assertEqual(mode, "already-present")

    def test_original_overwrite_semantics_survive_context_rewrite_without_race(self):
        base = [{"role": "user", "content": "old-1"}, {"role": "assistant", "content": "old-2"}]
        proposed = [{"role": "user", "content": "compacted"}, {"role": "assistant", "content": "new"}]
        merged, mode = merge_parallel_history(base, base, proposed)
        self.assertEqual(merged, proposed)
        self.assertEqual(mode, "original-overwrite")


if __name__ == "__main__":
    unittest.main()
