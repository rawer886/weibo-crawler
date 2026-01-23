"""
数据库操作模块
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from config import DATABASE_PATH


def init_database():
    """初始化数据库，创建表结构"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 博主表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bloggers (
                uid TEXT PRIMARY KEY,
                nickname TEXT,
                description TEXT,
                followers_count INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 微博表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                mid TEXT PRIMARY KEY,
                uid TEXT NOT NULL,
                content TEXT,
                created_at TEXT,
                reposts_count INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                likes_count INTEGER DEFAULT 0,
                is_repost INTEGER DEFAULT 0,
                repost_uid TEXT,
                repost_nickname TEXT,
                repost_content TEXT,
                images TEXT,
                local_images TEXT,
                video_url TEXT,
                source_url TEXT,
                crawled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uid) REFERENCES bloggers(uid)
            )
        """)

        # 评论表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id TEXT UNIQUE,
                mid TEXT NOT NULL,
                uid TEXT,
                nickname TEXT,
                content TEXT,
                created_at TEXT,
                likes_count INTEGER DEFAULT 0,
                is_blogger_reply INTEGER DEFAULT 0,
                reply_to_comment_id TEXT,
                reply_to_uid TEXT,
                reply_to_nickname TEXT,
                reply_to_content TEXT,
                crawled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mid) REFERENCES posts(mid)
            )
        """)

        # 抓取进度表（记录每个博主抓到哪了）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawl_progress (
                uid TEXT PRIMARY KEY,
                newest_mid TEXT,
                oldest_mid TEXT,
                newest_created_at TEXT,
                oldest_created_at TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_uid ON posts(uid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_mid ON comments(mid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_likes ON comments(likes_count)")

        conn.commit()
        print("数据库初始化完成")


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def save_blogger(blogger: dict):
    """保存或更新博主信息"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bloggers (uid, nickname, description, followers_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                nickname = excluded.nickname,
                description = excluded.description,
                followers_count = excluded.followers_count,
                updated_at = excluded.updated_at
        """, (
            blogger["uid"],
            blogger.get("nickname"),
            blogger.get("description"),
            blogger.get("followers_count"),
            datetime.now().isoformat()
        ))
        conn.commit()


def save_post(post: dict) -> bool:
    """
    保存微博，如果已存在则跳过
    返回: True 表示新增，False 表示已存在
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 检查是否已存在
        cursor.execute("SELECT mid FROM posts WHERE mid = ?", (post["mid"],))
        if cursor.fetchone():
            return False

        # images 使用 JSON 格式存储，避免 URL 中的特殊字符问题
        images_json = json.dumps(post.get("images", []), ensure_ascii=False)

        cursor.execute("""
            INSERT INTO posts (mid, uid, content, created_at, reposts_count,
                             comments_count, likes_count, is_repost,
                             repost_uid, repost_nickname, repost_content,
                             images, local_images, video_url, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post["mid"],
            post["uid"],
            post.get("content"),
            post.get("created_at"),
            post.get("reposts_count", 0),
            post.get("comments_count", 0),
            post.get("likes_count", 0),
            1 if post.get("is_repost") else 0,
            post.get("repost_uid"),
            post.get("repost_nickname"),
            post.get("repost_content"),
            images_json,
            post.get("local_images"),  # JSON 格式的本地图片路径列表
            post.get("video_url"),
            post.get("source_url"),
        ))
        conn.commit()
        return True


def save_comment(comment: dict) -> bool:
    """
    保存评论，如果已存在则跳过
    返回: True 表示新增，False 表示已存在
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 检查是否已存在
        cursor.execute("SELECT id FROM comments WHERE comment_id = ?", (comment["comment_id"],))
        if cursor.fetchone():
            return False

        cursor.execute("""
            INSERT INTO comments (comment_id, mid, uid, nickname, content,
                                created_at, likes_count, is_blogger_reply,
                                reply_to_comment_id, reply_to_uid, reply_to_nickname, reply_to_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            comment["comment_id"],
            comment["mid"],
            comment.get("uid"),
            comment.get("nickname"),
            comment.get("content"),
            comment.get("created_at"),
            comment.get("likes_count", 0),
            1 if comment.get("is_blogger_reply") else 0,
            comment.get("reply_to_comment_id"),
            comment.get("reply_to_uid"),
            comment.get("reply_to_nickname"),
            comment.get("reply_to_content"),
        ))
        conn.commit()
        return True


def is_post_exists(mid: str) -> bool:
    """检查微博是否已存在"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mid FROM posts WHERE mid = ?", (mid,))
        return cursor.fetchone() is not None


def get_blogger_post_count(uid: str) -> int:
    """获取某博主已抓取的微博数量"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posts WHERE uid = ?", (uid,))
        return cursor.fetchone()[0]


def get_stats() -> dict:
    """获取统计信息"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM bloggers")
        bloggers_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM posts")
        posts_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM comments")
        comments_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT uid, COUNT(*) as cnt FROM posts GROUP BY uid
        """)
        posts_by_blogger = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "bloggers_count": bloggers_count,
            "posts_count": posts_count,
            "comments_count": comments_count,
            "posts_by_blogger": posts_by_blogger,
        }


def get_recent_posts(limit: int = 20) -> list:
    """获取最近抓取的微博"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, b.nickname
            FROM posts p
            LEFT JOIN bloggers b ON p.uid = b.uid
            ORDER BY p.crawled_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_crawl_progress(uid: str) -> Optional[dict]:
    """获取某博主的抓取进度"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM crawl_progress WHERE uid = ?", (uid,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_crawl_progress(uid: str, mid: str, created_at: str, is_newer: bool):
    """
    更新抓取进度
    is_newer=True: 更新最新边界（向前抓新微博时）
    is_newer=False: 更新最老边界（向后抓历史时）
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 获取当前进度
        cursor.execute("SELECT * FROM crawl_progress WHERE uid = ?", (uid,))
        row = cursor.fetchone()

        if row is None:
            # 首次记录
            cursor.execute("""
                INSERT INTO crawl_progress (uid, newest_mid, oldest_mid, newest_created_at, oldest_created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uid, mid, mid, created_at, created_at, datetime.now().isoformat()))
        else:
            if is_newer:
                # 更新最新边界
                cursor.execute("""
                    UPDATE crawl_progress
                    SET newest_mid = ?, newest_created_at = ?, updated_at = ?
                    WHERE uid = ?
                """, (mid, created_at, datetime.now().isoformat(), uid))
            else:
                # 更新最老边界
                cursor.execute("""
                    UPDATE crawl_progress
                    SET oldest_mid = ?, oldest_created_at = ?, updated_at = ?
                    WHERE uid = ?
                """, (mid, created_at, datetime.now().isoformat(), uid))

        conn.commit()


def get_blogger_oldest_mid(uid: str) -> Optional[str]:
    """获取某博主已抓取的最老微博ID（用于继续向后抓取）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mid FROM posts WHERE uid = ? ORDER BY created_at ASC LIMIT 1
        """, (uid,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_blogger_newest_mid(uid: str) -> Optional[str]:
    """获取某博主已抓取的最新微博ID（用于检测新微博）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mid FROM posts WHERE uid = ? ORDER BY created_at DESC LIMIT 1
        """, (uid,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_post_comment_count(mid: str) -> int:
    """获取某条微博已抓取的评论数量"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM comments WHERE mid = ?", (mid,))
        return cursor.fetchone()[0]


def update_post_local_images(mid: str, local_images: list):
    """更新微博的本地图片路径"""
    import json
    with get_connection() as conn:
        cursor = conn.cursor()
        local_images_json = json.dumps(local_images, ensure_ascii=False)
        cursor.execute("""
            UPDATE posts SET local_images = ? WHERE mid = ?
        """, (local_images_json, mid))
        conn.commit()
