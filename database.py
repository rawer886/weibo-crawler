"""
数据库操作模块
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """初始化数据库，创建表结构"""
    with get_connection() as conn:
        cursor = conn.cursor()

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
                comment_pending INTEGER DEFAULT 0,
                crawled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uid) REFERENCES bloggers(uid)
            )
        """)

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
                images TEXT,
                local_images TEXT,
                crawled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mid) REFERENCES posts(mid)
            )
        """)

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

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_uid ON posts(uid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_mid ON comments(mid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_likes ON comments(likes_count)")

        conn.commit()
        logger.info("数据库初始化完成")


def save_blogger(blogger: dict):
    """保存或更新博主信息"""
    with get_connection() as conn:
        conn.execute("""
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
    """保存微博，已存在则跳过。返回 True 表示新增"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM posts WHERE mid = ?", (post["mid"],))
        if cursor.fetchone():
            return False

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
            json.dumps(post.get("images", []), ensure_ascii=False),
            post.get("local_images"),
            post.get("video_url"),
            post.get("source_url"),
        ))
        conn.commit()
        return True


def update_post(post: dict) -> bool:
    """更新已存在的微博数据。返回 True 表示更新成功"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE posts SET
                content = ?, created_at = ?, reposts_count = ?, comments_count = ?,
                likes_count = ?, is_repost = ?, repost_uid = ?, repost_nickname = ?,
                repost_content = ?, images = ?, video_url = ?, source_url = ?
            WHERE mid = ?
        """, (
            post.get("content"),
            post.get("created_at"),
            post.get("reposts_count", 0),
            post.get("comments_count", 0),
            post.get("likes_count", 0),
            1 if post.get("is_repost") else 0,
            post.get("repost_uid"),
            post.get("repost_nickname"),
            post.get("repost_content"),
            json.dumps(post.get("images", []), ensure_ascii=False),
            post.get("video_url"),
            post.get("source_url"),
            post["mid"],
        ))
        conn.commit()
        return cursor.rowcount > 0


def save_comment(comment: dict) -> bool:
    """保存评论，已存在则跳过。返回 True 表示新增"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM comments WHERE comment_id = ?", (comment["comment_id"],))
        if cursor.fetchone():
            return False

        images = comment.get("images")
        local_images = comment.get("local_images")

        cursor.execute("""
            INSERT INTO comments (comment_id, mid, uid, nickname, content,
                                created_at, likes_count, is_blogger_reply,
                                reply_to_comment_id, reply_to_uid, reply_to_nickname,
                                reply_to_content, images, local_images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(images, ensure_ascii=False) if images else None,
            json.dumps(local_images, ensure_ascii=False) if local_images else None,
        ))
        conn.commit()
        return True


def save_comments_batch(comments: list[dict]) -> int:
    """批量保存评论。返回新增数量"""
    if not comments:
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        new_count = 0

        for comment in comments:
            cursor.execute("SELECT 1 FROM comments WHERE comment_id = ?", (comment["comment_id"],))
            if cursor.fetchone():
                continue

            images = comment.get("images")
            local_images = comment.get("local_images")

            cursor.execute("""
                INSERT INTO comments (comment_id, mid, uid, nickname, content,
                                    created_at, likes_count, is_blogger_reply,
                                    reply_to_comment_id, reply_to_uid, reply_to_nickname,
                                    reply_to_content, images, local_images)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(images, ensure_ascii=False) if images else None,
                json.dumps(local_images, ensure_ascii=False) if local_images else None,
            ))
            new_count += 1

        conn.commit()
        return new_count


def is_post_exists(mid: str) -> bool:
    """检查微博是否已存在"""
    with get_connection() as conn:
        cursor = conn.execute("SELECT 1 FROM posts WHERE mid = ?", (mid,))
        return cursor.fetchone() is not None


def get_blogger_post_count(uid: str) -> int:
    """获取某博主已抓取的微博数量"""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM posts WHERE uid = ?", (uid,))
        return cursor.fetchone()[0]


def get_post_comment_count(mid: str) -> int:
    """获取某条微博已抓取的评论数量"""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM comments WHERE mid = ?", (mid,))
        return cursor.fetchone()[0]


def get_stats() -> dict:
    """获取统计信息"""
    with get_connection() as conn:
        bloggers = conn.execute("SELECT COUNT(*) FROM bloggers").fetchone()[0]
        posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        comments = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]

        rows = conn.execute("SELECT uid, COUNT(*) FROM posts GROUP BY uid").fetchall()
        posts_by_blogger = {row[0]: row[1] for row in rows}

        return {
            "bloggers_count": bloggers,
            "posts_count": posts,
            "comments_count": comments,
            "posts_by_blogger": posts_by_blogger,
        }


def get_recent_posts(limit: int = 20) -> list:
    """获取最近抓取的微博"""
    with get_connection() as conn:
        cursor = conn.execute("""
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
        row = conn.execute("SELECT * FROM crawl_progress WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None


def update_crawl_progress(uid: str, mid: str, created_at: str, is_newer: bool):
    """更新抓取进度。is_newer=True 更新最新边界，False 更新最老边界"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM crawl_progress WHERE uid = ?", (uid,)).fetchone()
        now = datetime.now().isoformat()

        if row is None:
            conn.execute("""
                INSERT INTO crawl_progress (uid, newest_mid, oldest_mid, newest_created_at, oldest_created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uid, mid, mid, created_at, created_at, now))
        elif is_newer:
            conn.execute("""
                UPDATE crawl_progress SET newest_mid = ?, newest_created_at = ?, updated_at = ? WHERE uid = ?
            """, (mid, created_at, now, uid))
        else:
            conn.execute("""
                UPDATE crawl_progress SET oldest_mid = ?, oldest_created_at = ?, updated_at = ? WHERE uid = ?
            """, (mid, created_at, now, uid))

        conn.commit()


def get_blogger_oldest_mid(uid: str) -> Optional[str]:
    """获取某博主已抓取的最老微博ID"""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT mid FROM posts WHERE uid = ? ORDER BY created_at ASC LIMIT 1
        """, (uid,)).fetchone()
        return row[0] if row else None


def get_blogger_newest_mid(uid: str) -> Optional[str]:
    """获取某博主已抓取的最新微博ID"""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT mid FROM posts WHERE uid = ? ORDER BY created_at DESC LIMIT 1
        """, (uid,)).fetchone()
        return row[0] if row else None


def update_post_local_images(mid: str, local_images: list):
    """更新微博的本地图片路径"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET local_images = ? WHERE mid = ?",
            (json.dumps(local_images, ensure_ascii=False), mid)
        )
        conn.commit()


def set_comment_pending(mid: str, pending: bool = True):
    """设置微博的评论待更新标记"""
    with get_connection() as conn:
        conn.execute("UPDATE posts SET comment_pending = ? WHERE mid = ?", (1 if pending else 0, mid))
        conn.commit()


def get_pending_comment_posts(uid: str, stable_days: int) -> list:
    """获取需要更新评论的微博（发布时间超过 stable_days 天且 comment_pending=1）"""
    cutoff_date = (datetime.now() - timedelta(days=stable_days)).strftime("%y-%m-%d %H:%M")
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT mid, uid, content, created_at, comments_count
            FROM posts
            WHERE uid = ? AND comment_pending = 1 AND created_at < ?
            ORDER BY created_at DESC
        """, (uid, cutoff_date))
        return [dict(row) for row in cursor.fetchall()]


def clear_comment_pending(mid: str):
    """清除微博的评论待更新标记"""
    with get_connection() as conn:
        conn.execute("UPDATE posts SET comment_pending = 0 WHERE mid = ?", (mid,))
        conn.commit()


def clear_comments_for_post(mid: str) -> int:
    """清除某条微博的所有评论"""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM comments WHERE mid = ?", (mid,))
        conn.commit()
        return cursor.rowcount


def delete_post(mid: str) -> bool:
    """删除微博及其所有评论"""
    with get_connection() as conn:
        # 先删除评论
        conn.execute("DELETE FROM comments WHERE mid = ?", (mid,))
        # 再删除微博
        cursor = conn.execute("DELETE FROM posts WHERE mid = ?", (mid,))
        conn.commit()
        return cursor.rowcount > 0


def get_post_with_blogger(mid: str) -> Optional[dict]:
    """获取微博及博主信息"""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT p.*, b.nickname as blogger_nickname
            FROM posts p
            LEFT JOIN bloggers b ON p.uid = b.uid
            WHERE p.mid = ?
        """, (mid,)).fetchone()
        return dict(row) if row else None


def get_comments_by_mid(mid: str, blogger_only: bool = False) -> list:
    """获取微博的评论列表"""
    with get_connection() as conn:
        if blogger_only:
            cursor = conn.execute("""
                SELECT * FROM comments
                WHERE mid = ? AND is_blogger_reply = 1
                ORDER BY likes_count DESC, created_at ASC
            """, (mid,))
        else:
            cursor = conn.execute("""
                SELECT * FROM comments
                WHERE mid = ?
                ORDER BY likes_count DESC, created_at ASC
            """, (mid,))
        return [dict(row) for row in cursor.fetchall()]


def get_blogger(uid: str) -> Optional[dict]:
    """获取博主信息"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM bloggers WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None


def update_comment_likes(comment_id: str, likes_count: int) -> bool:
    """更新评论点赞数。返回 True 表示已更新"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE comments SET likes_count = ? WHERE comment_id = ?",
            (likes_count, comment_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_blogger_comments(uid: str) -> list:
    """获取博主的所有评论（含微博上下文）"""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT c.*, p.content as post_content, p.created_at as post_created_at
            FROM comments c
            LEFT JOIN posts p ON c.mid = p.mid
            WHERE c.is_blogger_reply = 1 AND p.uid = ?
            ORDER BY c.created_at DESC
        """, (uid,))
        return [dict(row) for row in cursor.fetchall()]
