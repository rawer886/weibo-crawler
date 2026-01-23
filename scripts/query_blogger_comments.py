"""
查询特定微博下博主自己的评论
"""
import sqlite3
import sys
import os

# 添加父目录到路径，以便导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH


def query_blogger_comments(mid: str):
    """
    查询特定微博下博主自己的评论

    参数:
        mid: 微博ID
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 先查询微博信息
    cursor.execute("""
        SELECT p.*, b.nickname as blogger_nickname
        FROM posts p
        LEFT JOIN bloggers b ON p.uid = b.uid
        WHERE p.mid = ?
    """, (mid,))

    post = cursor.fetchone()

    if not post:
        print(f"❌ 未找到微博: {mid}")
        conn.close()
        return

    # 查询该微博下博主的评论
    cursor.execute("""
        SELECT *
        FROM comments
        WHERE mid = ? AND is_blogger_reply = 1
        ORDER BY created_at
    """, (mid,))

    blogger_comments = cursor.fetchall()

    # 输出结果
    print("=" * 80)
    print(f"微博ID: {post['mid']}")
    print(f"博主: {post['blogger_nickname'] or post['uid']}")
    print(f"发布时间: {post['created_at']}")
    print(f"微博内容: {post['content'][:100]}{'...' if len(post['content']) > 100 else ''}")
    print(f"评论数: {post['comments_count']}")
    print("=" * 80)
    print()

    if not blogger_comments:
        print("❌ 该微博下没有找到博主自己的评论")
    else:
        print(f"✅ 找到 {len(blogger_comments)} 条博主评论：")
        print()

        for i, comment in enumerate(blogger_comments, 1):
            print(f"【评论 {i}】")
            print(f"  评论ID: {comment['comment_id']}")
            print(f"  时间: {comment['created_at'] or '未知'}")
            print(f"  点赞数: {comment['likes_count']}")
            print(f"  📝 评论内容: {comment['content']}")

            # 显示回复关系
            if comment['reply_to_comment_id']:
                # 回复其他评论
                # 优先使用新字段 reply_to_nickname 和 reply_to_uid
                try:
                    reply_to_nickname = comment['reply_to_nickname']
                    reply_to_uid = comment['reply_to_uid']
                except (KeyError, IndexError):
                    # 字段不存在（旧数据）
                    reply_to_nickname = None
                    reply_to_uid = None

                # 构建回复信息
                reply_info = ""
                if reply_to_nickname:
                    reply_info = f"@{reply_to_nickname}"
                else:
                    # 兼容旧数据：尝试从数据库中查找被回复的评论
                    cursor.execute("""
                        SELECT * FROM comments
                        WHERE comment_id = ? AND mid = ?
                    """, (comment['reply_to_comment_id'], mid))

                    replied_comment = cursor.fetchone()

                    if replied_comment:
                        reply_info = f"@{replied_comment['nickname']}"
                    else:
                        reply_info = f"@{comment['reply_to_comment_id']}"

                # 显示 @用户名 和被回复的内容在同一行
                if comment['reply_to_content']:
                    content_preview = comment['reply_to_content'][:100] + ('...' if len(comment['reply_to_content']) > 100 else '')
                    print(f"  ↳ {reply_info}: {content_preview}")
                else:
                    print(f"  ↳ {reply_info}")
            # 如果是直接评论微博，不显示被评论内容

            print()

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python query_blogger_comments.py <微博ID>")
        print("示例: python query_blogger_comments.py 5253489136775271")
        sys.exit(1)

    mid = sys.argv[1]
    query_blogger_comments(mid)
