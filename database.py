"""
数据库操作模块
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from config import DATABASE_PATH
from logger import get_logger

logger = get_logger(__name__)


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
                created_at TEXT,
                reposts_count INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                likes_count INTEGER DEFAULT 0,
                is_repost INTEGER DEFAULT 0,
                source_url TEXT,
                detail_status INTEGER DEFAULT 0,
                crawled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                content TEXT,
                repost_content TEXT,
                media TEXT,
                repost_media TEXT,
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
                list_scan_oldest_mid TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_uid ON posts(uid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_mid ON comments(mid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_likes ON comments(likes_count)")

        conn.commit()


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


def _build_media(images: list, video: dict) -> Optional[dict]:
    """构建媒体对象，返回 None 表示无媒体"""
    media = {}
    if images:
        media["images"] = [{"url": url} for url in images]
    if video:
        media["video"] = video
    return media or None


def _serialize_media(media: Optional[dict]) -> Optional[str]:
    """序列化媒体对象为 JSON 字符串"""
    return json.dumps(media, ensure_ascii=False) if media else None


def _insert_post(cursor, post: dict, detail_status: int = 1):
    """插入微博记录（内部函数）"""
    media = _build_media(post.get("images", []), post.get("video"))
    repost_media = _build_media(post.get("repost_images", []), post.get("repost_video"))

    cursor.execute("""
        INSERT INTO posts (mid, uid, created_at, reposts_count, comments_count,
                         likes_count, is_repost, source_url, detail_status,
                         content, repost_content, media, repost_media)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post["mid"],
        post["uid"],
        post.get("created_at"),
        post.get("reposts_count", 0),
        post.get("comments_count", 0),
        post.get("likes_count", 0),
        1 if post.get("is_repost") else 0,
        post.get("source_url"),
        detail_status,
        post.get("content"),
        post.get("repost_content"),
        _serialize_media(media),
        _serialize_media(repost_media),
    ))


def save_post(post: dict, stable_days: int = None) -> bool:
    """保存微博，已存在则跳过。返回 True 表示新增

    参数:
        stable_days: 如果提供，则发布时间在 stable_days 内的微博 detail_status 设为 0
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM posts WHERE mid = ?", (post["mid"],))
        if cursor.fetchone():
            return False

        # 根据时间判断 detail_status
        detail_status = 1
        if stable_days is not None:
            created_at = post.get("created_at")
            if created_at:
                try:
                    post_date = datetime.strptime(created_at, "%Y-%m-%d %H:%M")
                    cutoff = datetime.now() - timedelta(days=stable_days)
                    if post_date >= cutoff:
                        detail_status = 0
                except Exception:
                    pass

        _insert_post(cursor, post, detail_status=detail_status)
        conn.commit()
        return True


def update_post(post: dict) -> bool:
    """更新已存在的微博数据。返回 True 表示更新成功"""
    with get_connection() as conn:
        cursor = conn.cursor()

        media = _build_media(post.get("images", []), post.get("video"))
        repost_media = _build_media(post.get("repost_images", []), post.get("repost_video"))

        cursor.execute("""
            UPDATE posts SET
                content = ?, created_at = ?, reposts_count = ?, comments_count = ?,
                likes_count = ?, is_repost = ?, repost_content = ?, repost_media = ?,
                media = ?, source_url = ?
            WHERE mid = ?
        """, (
            post.get("content"),
            post.get("created_at"),
            post.get("reposts_count", 0),
            post.get("comments_count", 0),
            post.get("likes_count", 0),
            1 if post.get("is_repost") else 0,
            post.get("repost_content"),
            _serialize_media(repost_media),
            _serialize_media(media),
            post.get("source_url"),
            post["mid"],
        ))
        conn.commit()
        return cursor.rowcount > 0


def _insert_comment(cursor, comment: dict):
    """插入评论记录（内部函数）"""
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


def save_comment(comment: dict) -> bool:
    """保存评论，已存在则跳过。返回 True 表示新增"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM comments WHERE comment_id = ?", (comment["comment_id"],))
        if cursor.fetchone():
            return False

        _insert_comment(cursor, comment)
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

            _insert_comment(cursor, comment)
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


def _update_media_local_images(mid: str, local_images: list, column: str):
    """更新媒体字段中图片的本地路径（内部函数）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {column} FROM posts WHERE mid = ?", (mid,))
        row = cursor.fetchone()
        if not row:
            return

        media = json.loads(row[0]) if row[0] else {}
        images = media.get("images", [])

        for i, local_path in enumerate(local_images):
            if i < len(images):
                images[i]["local"] = local_path

        media["images"] = images
        conn.execute(
            f"UPDATE posts SET {column} = ? WHERE mid = ?",
            (_serialize_media(media), mid)
        )
        conn.commit()


def update_post_local_images(mid: str, local_images: list):
    """更新微博的本地图片路径"""
    _update_media_local_images(mid, local_images, "media")


def update_post_repost_local_images(mid: str, local_images: list):
    """更新原微博的本地图片路径"""
    _update_media_local_images(mid, local_images, "repost_media")


def delete_comments_by_mid(mid: str) -> int:
    """删除指定微博的所有评论（包含级联评论）。返回删除数量"""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM comments WHERE mid = ?", (mid,))
        conn.commit()
        return cursor.rowcount


def delete_post_only(mid: str) -> bool:
    """仅删除微博本身（不删除评论）。返回是否删除成功"""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM posts WHERE mid = ?", (mid,))
        conn.commit()
        return cursor.rowcount > 0


def delete_post(mid: str) -> bool:
    """删除微博及其所有评论"""
    delete_comments_by_mid(mid)
    return delete_post_only(mid)


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


# ==================== 两阶段抓取相关函数 ====================


def save_post_from_list(post: dict) -> bool:
    """从列表数据保存微博（detail_status=0），已存在则跳过。返回 True 表示新增"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM posts WHERE mid = ?", (post["mid"],))
        if cursor.fetchone():
            return False

        _insert_post(cursor, post, detail_status=0)
        conn.commit()
        return True


def get_posts_pending_detail(uid: str, stable_days: int, limit: int = 50) -> list:
    """获取需要抓取详情的微博

    条件：detail_status=0（未抓详情）且超过 stable_days
    按 created_at DESC 排序
    """
    cutoff_date = (datetime.now() - timedelta(days=stable_days)).strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT mid, uid, content, created_at, comments_count, detail_status
            FROM posts
            WHERE uid = ? AND created_at < ? AND detail_status = 0
            ORDER BY created_at DESC
            LIMIT ?
        """, (uid, cutoff_date, limit))
        return [dict(row) for row in cursor.fetchall()]


def mark_post_detail_done(mid: str):
    """标记微博详情已抓取，只设置 detail_status=1"""
    with get_connection() as conn:
        conn.execute("UPDATE posts SET detail_status = 1 WHERE mid = ?", (mid,))
        conn.commit()


def get_list_scan_oldest_mid(uid: str) -> Optional[str]:
    """获取列表扫描的最老微博 ID"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT list_scan_oldest_mid FROM crawl_progress WHERE uid = ?", (uid,)
        ).fetchone()
        return row[0] if row and row[0] else None


def update_list_scan_oldest_mid(uid: str, mid: str):
    """更新列表扫描进度"""
    with get_connection() as conn:
        now = datetime.now().isoformat()
        conn.execute("""
            INSERT INTO crawl_progress (uid, list_scan_oldest_mid, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET list_scan_oldest_mid = ?, updated_at = ?
        """, (uid, mid, now, mid, now))
        conn.commit()


def get_blogger_stats(uid: str) -> Optional[dict]:
    """获取博主的详细统计信息"""
    with get_connection() as conn:
        # 博主基本信息
        blogger = conn.execute(
            "SELECT * FROM bloggers WHERE uid = ?", (uid,)
        ).fetchone()
        if not blogger:
            return None

        # 微博统计
        posts_stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN detail_status = 0 THEN 1 ELSE 0 END) as pending_detail,
                SUM(CASE WHEN detail_status = 1 THEN 1 ELSE 0 END) as detail_done,
                MIN(created_at) as oldest_post_time,
                MAX(created_at) as newest_post_time
            FROM posts WHERE uid = ?
        """, (uid,)).fetchone()

        # 评论统计
        comments_stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_blogger_reply = 1 THEN 1 ELSE 0 END) as blogger_replies
            FROM comments c
            JOIN posts p ON c.mid = p.mid
            WHERE p.uid = ?
        """, (uid,)).fetchone()

        # 抓取进度
        progress = conn.execute(
            "SELECT * FROM crawl_progress WHERE uid = ?", (uid,)
        ).fetchone()

        return {
            "blogger": dict(blogger),
            "posts": dict(posts_stats) if posts_stats else {},
            "comments": dict(comments_stats) if comments_stats else {},
            "progress": dict(progress) if progress else {}
        }
