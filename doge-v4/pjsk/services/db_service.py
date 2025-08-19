import aiosqlite
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from astrbot.api import logger

class DBService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_conn(self) -> aiosqlite.Connection:
        """
        [正确模式] 返回一个 aiosqlite 连接对象（Awaitable），
        由调用方的 `async with` 来管理其生命周期。
        """
        return aiosqlite.connect(self.db_path)

    async def _ensure_user_exists(self, cursor: aiosqlite.Cursor, user_id: str, user_name: str):
        """确保用户在数据库中存在，如果不存在则创建。"""
        await cursor.execute("SELECT 1 FROM user_stats WHERE user_id = ?", (user_id,))
        if await cursor.fetchone() is None:
            today = datetime.now().strftime("%Y-%m-%d")
            columns = [
                "user_id", "user_name", "score", "attempts", "correct_attempts",
                "daily_games_played", "last_played_date", "daily_listen_songs",
                "last_listen_date", "correct_streak", "max_correct_streak", "group_scores"
            ]
            default_values = (user_id, user_name, 0, 0, 0, 0, today, 0, today, 0, 0, '{}')
            placeholders = ','.join(['?'] * len(columns))
            await cursor.execute(f"INSERT INTO user_stats ({', '.join(columns)}) VALUES ({placeholders})", default_values)

    async def init_db(self):
        """初始化数据库，创建表结构。"""
        async with self._get_conn() as conn:
            # 在user_stats表中将user_id设为主键，以保证数据的唯一性。
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id TEXT PRIMARY KEY, user_name TEXT, score INTEGER DEFAULT 0,
                    attempts INTEGER DEFAULT 0, correct_attempts INTEGER DEFAULT 0,
                    last_played_date TEXT, daily_games_played INTEGER DEFAULT 0,
                    last_listen_date TEXT, daily_listen_songs INTEGER DEFAULT 0,
                    group_scores TEXT DEFAULT '{}', correct_streak INTEGER DEFAULT 0,
                    max_correct_streak INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS mode_stats (
                    mode TEXT PRIMARY KEY, total_attempts INTEGER DEFAULT 0, correct_attempts INTEGER DEFAULT 0
                )
            """)
            await conn.commit()

    async def update_stats(self, session_id: str, user_id: str, user_name: str, score: int, correct: bool):
        """异步更新用户统计数据，并能健壮地处理数据库中的脏数据。"""
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await self._ensure_user_exists(cursor, user_id, user_name)
                
                await cursor.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
                user_stats = await cursor.fetchone()

                def safe_int(key: str) -> int:
                    """一个安全的转换函数，用于处理可能存在的脏数据。"""
                    if key not in user_stats.keys():
                        return 0
                    value = user_stats[key]
                    if value is None:
                        return 0
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        logger.warning(f"Corrupted data for user {user_id}, key '{key}': '{value}'. Treating as 0.")
                        return 0

                attempts = safe_int('attempts') + 1
                correct_attempts = safe_int('correct_attempts')
                current_score = safe_int('score')
                correct_streak = safe_int('correct_streak')
                max_correct_streak = safe_int('max_correct_streak')

                if correct:
                    correct_attempts += 1
                    current_score += score
                    correct_streak += 1
                    max_correct_streak = max(max_correct_streak, correct_streak)
                else:
                    correct_streak = 0

                group_scores_str = user_stats['group_scores'] if 'group_scores' in user_stats.keys() else '{}'
                group_scores = json.loads(group_scores_str or '{}')
                group_stat = group_scores.get(session_id, {"score": 0, "attempts": 0, "correct_attempts": 0})
                if isinstance(group_stat, int):
                    group_stat = {"score": group_stat, "attempts": 0, "correct_attempts": 0}

                group_stat["score"] += score
                group_stat["attempts"] += 1
                if correct: group_stat["correct_attempts"] += 1
                group_scores[session_id] = group_stat
                
                await cursor.execute("""
                    UPDATE user_stats SET user_name=?, score=?, attempts=?, correct_attempts=?, 
                                          correct_streak=?, max_correct_streak=?, group_scores=?
                    WHERE user_id = ?
                """, (user_name, current_score, attempts, correct_attempts,
                      correct_streak, max_correct_streak, json.dumps(group_scores), user_id))
                await conn.commit()

    async def consume_daily_play_attempt(self, user_id: str, user_name: str):
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await self._ensure_user_exists(cursor, user_id, user_name)
                await cursor.execute("SELECT daily_games_played, last_played_date FROM user_stats WHERE user_id = ?", (user_id,))
                row = await cursor.fetchone()
                
                today = datetime.now().strftime("%Y-%m-%d")
                daily_games = row['daily_games_played'] if row and row['last_played_date'] == today else 0
                
                await cursor.execute("UPDATE user_stats SET daily_games_played = ?, last_played_date = ?, user_name = ? WHERE user_id = ?",
                                     ((daily_games or 0) + 1, today, user_name, user_id))
                await conn.commit()

    async def can_play(self, user_id: str, daily_limit: int) -> bool:
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT daily_games_played, last_played_date FROM user_stats WHERE user_id = ?", (user_id,))
                row = await cursor.fetchone()
                if not row or row['last_played_date'] != datetime.now().strftime("%Y-%m-%d"):
                    return True
                return (row['daily_games_played'] or 0) < daily_limit

    async def record_listen_song(self, user_id: str, user_name: str):
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await self._ensure_user_exists(cursor, user_id, user_name)
                await cursor.execute("SELECT daily_listen_songs, last_listen_date FROM user_stats WHERE user_id = ?", (user_id,))
                row = await cursor.fetchone()
                
                today = datetime.now().strftime("%Y-%m-%d")
                daily_listen = row['daily_listen_songs'] if row and row['last_listen_date'] == today else 0
                
                await cursor.execute("UPDATE user_stats SET daily_listen_songs = ?, last_listen_date = ?, user_name = ? WHERE user_id = ?",
                                     ((daily_listen or 0) + 1, today, user_name, user_id))
                await conn.commit()

    async def can_listen_song(self, user_id: str, daily_limit: int) -> bool:
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT daily_listen_songs, last_listen_date FROM user_stats WHERE user_id = ?", (user_id,))
                row = await cursor.fetchone()
                if not row or row['last_listen_date'] != datetime.now().strftime("%Y-%m-%d"):
                    return True
                return (row['daily_listen_songs'] or 0) < daily_limit

    async def get_user_daily_limits(self, user_id: str) -> Tuple[bool, int]:
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT daily_listen_songs, last_listen_date FROM user_stats WHERE user_id = ?", (user_id,))
                row = await cursor.fetchone()
                if not row or row['last_listen_date'] != datetime.now().strftime("%Y-%m-%d"):
                    return True, 0
                return True, (row['daily_listen_songs'] or 0)

    async def get_user_local_global_stats(self, user_id: str) -> Optional[Dict]:
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
                row = await cursor.fetchone()
                if not row: return None

                score = row['score'] or 0
                await cursor.execute("SELECT COUNT(1) + 1 FROM user_stats WHERE score > ?", (score,))
                rank_row = await cursor.fetchone()
                
                return {
                    'score': score, 'attempts': row['attempts'], 'correct': row['correct_attempts'],
                    'daily_plays': row['daily_games_played'] if row and row['last_played_date'] == datetime.now().strftime("%Y-%m-%d") else 0,
                    'last_play_date': row['last_played_date'], 'rank': rank_row[0] if rank_row else 1
                }
    
    async def reset_guess_limit(self, target_id: str) -> bool:
        async with self._get_conn() as conn:
            res = await conn.execute("UPDATE user_stats SET daily_games_played = 0 WHERE user_id = ?", (target_id,))
            await conn.commit()
            return res.rowcount > 0

    async def reset_listen_limit(self, target_id: str) -> bool:
        async with self._get_conn() as conn:
            res = await conn.execute("UPDATE user_stats SET daily_listen_songs = 0 WHERE user_id = ?", (target_id,))
            await conn.commit()
            return res.rowcount > 0
            
    async def get_all_user_stats(self) -> List[Tuple]:
        async with self._get_conn() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT user_id, user_name, score FROM user_stats WHERE score > 0")
                return await cursor.fetchall()
    
    async def get_group_ranking(self, session_id: str) -> List[Tuple]:
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT user_id, user_name, group_scores FROM user_stats")
                all_users_data = await cursor.fetchall()
            
            group_ranking = []
            for row in all_users_data:
                group_scores_str = row['group_scores'] if 'group_scores' in row.keys() else None
                if not group_scores_str: continue
                try:
                    group_scores = json.loads(group_scores_str)
                    group_stat_raw = group_scores.get(session_id)
                    if not group_stat_raw: continue
                    
                    if isinstance(group_stat_raw, int):
                        score, attempts, correct_attempts = group_stat_raw, -1, -1
                    else:
                        score = group_stat_raw.get("score", 0)
                        attempts = group_stat_raw.get("attempts", 0)
                        correct_attempts = group_stat_raw.get("correct_attempts", 0)
                    
                    if score > 0:
                        group_ranking.append((row['user_id'], row['user_name'], score, attempts, correct_attempts))
                except json.JSONDecodeError:
                    continue
            
            group_ranking.sort(key=lambda x: x[2], reverse=True)
            return group_ranking
            
    async def get_global_ranking_data(self) -> List[Tuple]:
        async with self._get_conn() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT user_id, user_name, SUM(score) as total_score, SUM(attempts) as total_attempts, 
                           SUM(correct_attempts) as total_correct
                    FROM user_stats GROUP BY user_id, user_name ORDER BY total_score DESC LIMIT 10
                """)
                return await cursor.fetchall()

    async def get_user_stats_in_group(self, user_id_to_find: str, session_id: str) -> Optional[Dict]:
        full_ranking = await self.get_group_ranking(session_id)
        for i, (user_id, _, score, attempts, correct_attempts) in enumerate(full_ranking):
            if user_id == user_id_to_find:
                return {"score": score, "rank": i + 1, "attempts": attempts, "correct_attempts": correct_attempts}
        
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT group_scores FROM user_stats WHERE user_id = ?", (user_id_to_find,))
                row = await cursor.fetchone()
            if row and 'group_scores' in row.keys() and row['group_scores']:
                try:
                    group_scores = json.loads(row['group_scores'])
                    stat = group_scores.get(session_id)
                    if isinstance(stat, dict):
                        return {"score": stat.get("score", 0), "rank": None, "attempts": stat.get("attempts", 0), "correct_attempts": stat.get("correct_attempts", 0)}
                    elif isinstance(stat, int):
                         return {"score": stat, "rank": None, "attempts": -1, "correct_attempts": -1}
                except json.JSONDecodeError:
                    pass
        return {"score": 0, "rank": None, "attempts": 0, "correct_attempts": 0}

    async def update_mode_stats(self, mode: str, correct: bool):
        async with self._get_conn() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT total_attempts, correct_attempts FROM mode_stats WHERE mode = ?", (mode,))
                row = await cursor.fetchone()
                if row:
                    await cursor.execute("UPDATE mode_stats SET total_attempts = ?, correct_attempts = ? WHERE mode = ?", 
                                         ((row['total_attempts'] or 0) + 1, (row['correct_attempts'] or 0) + (1 if correct else 0), mode))
                else:
                    await cursor.execute("INSERT INTO mode_stats (mode, total_attempts, correct_attempts) VALUES (?, ?, ?)",
                                         (mode, 1, 1 if correct else 0))
                await conn.commit()
    
    async def get_mode_stats(self) -> List[Tuple]:
        async with self._get_conn() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT mode, total_attempts, correct_attempts FROM mode_stats")
                return await cursor.fetchall()
    
    async def reset_mode_stats(self):
        async with self._get_conn() as conn:
            await conn.execute("DELETE FROM mode_stats")
            await conn.commit()
