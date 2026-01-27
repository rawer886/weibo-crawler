"""
删除指定微博的全部评论数据
"""
import sqlite3
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH


# ANSI 颜色代码
class Colors:
    CYAN = '\033[96m'      # 青色 - 用于普通用户名
    YELLOW = '\033[93m'    # 黄色 - 用于博主名字
    RESET = '\033[0m'      # 重置颜色


def delete_comments_by_mid(mid: str):
    """删除指定微博的所有评论"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 查询该微博的评论数量
    cursor.execute("SELECT COUNT(*) as cnt FROM comments WHERE mid = ?", (mid,))
    count = cursor.fetchone()['cnt']

    if count == 0:
        print(f"微博 {mid} 没有评论数据")
        conn.close()
        return

    # 查询微博信息
    cursor.execute("""
        SELECT p.*, b.nickname as blogger_nickname
        FROM posts p
        LEFT JOIN bloggers b ON p.uid = b.uid
        WHERE p.mid = ?
    """, (mid,))
    post = cursor.fetchone()

    # 输出微博信息
    print("=" * 80)
    print(f"微博ID: {mid}")
    if post:
        print(f"博主: {post['blogger_nickname'] or post['uid']}")
        print(f"发布时间: {post['created_at']}")
        print(f"微博内容: {post['content'][:100]}{'...' if len(post['content'] or '') > 100 else ''}")
        print(f"点赞数: {post['likes_count']} | 转发数: {post['reposts_count']} | 评论数: {post['comments_count']}")
    else:
        print("微博正文: (未找到)")
    print("=" * 80)
    print()

    # 查询所有评论
    cursor.execute("""
        SELECT *
        FROM comments
        WHERE mid = ?
        ORDER BY likes_count DESC, created_at ASC
    """, (mid,))
    all_comments = cursor.fetchall()

    print(f"共找到 {len(all_comments)} 条评论（按热度排序）：")
    print()

    # 构建评论映射和回复关系
    comment_map = {comment['comment_id']: comment for comment in all_comments}
    replies_map = defaultdict(list)
    top_level_comments = []

    for comment in all_comments:
        reply_to_id = comment['reply_to_comment_id']
        if reply_to_id and reply_to_id in comment_map:
            replies_map[reply_to_id].append(comment)
        else:
            top_level_comments.append(comment)

    def print_comment(comment, level=0, floor_number=None):
        """打印评论"""
        indent = "  " * level
        is_blogger = comment['is_blogger_reply']
        nickname = comment['nickname'] or comment['uid']

        if is_blogger:
            user_info = f"{Colors.YELLOW}{nickname}🔥{Colors.RESET}"
        else:
            user_info = f"{Colors.CYAN}{nickname}{Colors.RESET}"

        likes_info = f"👍 {comment['likes_count']}"
        time_info = comment['created_at'] if comment['created_at'] else "未知"

        if level == 0:
            print(f"{indent}[{floor_number}] {user_info}: {comment['content']} ({time_info} {likes_info})")
        else:
            reply_to_info = ""
            if comment['reply_to_comment_id'] and comment['reply_to_nickname']:
                reply_to_nickname = comment['reply_to_nickname']
                reply_to_info = f"→@{Colors.CYAN}{reply_to_nickname}{Colors.RESET} "
            print(f"{indent}  ↳ {user_info} {reply_to_info}: {comment['content']} ({time_info} {likes_info})")

        if comment['comment_id'] in replies_map:
            sorted_replies = sorted(
                replies_map[comment['comment_id']],
                key=lambda x: x['likes_count'],
                reverse=True
            )
            for reply in sorted_replies:
                print_comment(reply, level + 1)

    for i, comment in enumerate(top_level_comments, 1):
        print_comment(comment, level=0, floor_number=i)

    # 用户确认
    print()
    print(f"即将删除微博 {mid} 的全部 {count} 条评论")
    response = input("确认删除吗？(y/n): ").strip().lower()

    if response != 'y':
        print("已取消删除")
        conn.close()
        return

    # 执行删除
    try:
        cursor.execute("DELETE FROM comments WHERE mid = ?", (mid,))
        conn.commit()
        print(f"成功删除 {count} 条评论")
    except Exception as e:
        conn.rollback()
        print(f"删除失败: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/delete_comments.py <微博ID>")
        print("示例: python scripts/delete_comments.py 5254891884513482")
        sys.exit(1)

    delete_comments_by_mid(sys.argv[1])
