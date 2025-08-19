import sqlite3

DB_PATH = "cube.sqlite"


class Rank:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """
        初始化数据库，仅保留 group_id 和耗时（毫秒级）。
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS group_duration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL UNIQUE,
                    duration INTEGER DEFAULT 0
                )
            """)

    def update_duration(self, group_id: str, duration: int):
        """
        设置指定群的耗时（毫秒），如无记录则插入。
        """
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM group_duration WHERE group_id=?", (group_id,)
            ).fetchone()
            if result:
                conn.execute(
                    "UPDATE group_duration SET duration=? WHERE group_id=?",
                    (duration, group_id),
                )
            else:
                conn.execute(
                    "INSERT INTO group_duration (group_id, duration) VALUES (?, ?)",
                    (group_id, duration),
                )

    def get_rank(self) -> str:
        """
        获取所有群聊的耗时排行榜（从小到大），返回秒数精确到小数点后三位。
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT group_id, duration FROM group_duration ORDER BY duration ASC"
            ).fetchall()

        return (
            "\n".join(
                f"{i + 1}. 群{group_id}     {duration / 1000:.3f}秒"  # 转换为秒并保留3位小数
                for i, (group_id, duration) in enumerate(rows)
            )
            or "暂无数据"
        )
