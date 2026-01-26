"""
展示指定微博的所有评论，按热度排序，支持楼层展示
"""
import sqlite3
import sys
import os
from collections import defaultdict

# 添加父目录到路径，以便导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH


# ANSI 颜色代码
class Colors:
    CYAN = '\033[96m'      # 青色 - 用于普通用户名
    YELLOW = '\033[93m'    # 黄色 - 用于博主名字
    RESET = '\033[0m'      # 重置颜色


def show_all_comments(mid: str):
    """
    展示特定微博的所有评论，按热度排序，支持楼层展示

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

    # 查询该微博的所有评论，按热度（点赞数）降序排列
    cursor.execute("""
        SELECT *
        FROM comments
        WHERE mid = ?
        ORDER BY likes_count DESC, created_at ASC
    """, (mid,))

    all_comments = cursor.fetchall()

    # 输出微博信息
    print("=" * 80)
    print(f"微博ID: {post['mid']}")
    print(f"博主: {post['blogger_nickname'] or post['uid']}")
    print(f"发布时间: {post['created_at']}")
    print(f"微博内容: {post['content'][:100]}{'...' if len(post['content']) > 100 else ''}")
    print(f"点赞数: {post['likes_count']} | 转发数: {post['reposts_count']} | 评论数: {post['comments_count']}")
    print("=" * 80)
    print()

    if not all_comments:
        print("❌ 该微博下没有找到评论")
        conn.close()
        return

    print(f"✅ 共找到 {len(all_comments)} 条评论（按热度排序）：")
    print()

    # 构建评论映射：comment_id -> comment
    comment_map = {comment['comment_id']: comment for comment in all_comments}

    # 构建回复关系：被回复的评论ID -> [回复它的评论列表]
    replies_map = defaultdict(list)

    # 顶层评论列表（没有 reply_to_comment_id 或者被回复的评论不存在的）
    top_level_comments = []

    for comment in all_comments:
        reply_to_id = comment['reply_to_comment_id']
        if reply_to_id and reply_to_id in comment_map:
            # 这是一个回复评论，加入到被回复评论的回复列表中
            replies_map[reply_to_id].append(comment)
        else:
            # 这是顶层评论
            top_level_comments.append(comment)

    # 递归打印评论及其回复
    def print_comment(comment, level=0, floor_number=None):
        """
        打印评论

        参数:
            comment: 评论数据
            level: 层级，0为顶层，1为一级回复，2为二级回复...
            floor_number: 楼层号（仅顶层评论显示）
        """
        indent = "  " * level

        # 构建用户信息（带颜色）
        is_blogger = comment['is_blogger_reply']
        nickname = comment['nickname'] or comment['uid']

        if is_blogger:
            # 博主用黄色显示，加上火焰标记
            user_info = f"{Colors.YELLOW}{nickname}🔥{Colors.RESET}"
        else:
            # 普通用户用青色显示
            user_info = f"{Colors.CYAN}{nickname}{Colors.RESET}"

        # 构建点赞和时间信息
        likes_info = f"👍 {comment['likes_count']}"
        time_info = comment['created_at'] if comment['created_at'] else "未知"  # 显示完整日期时间

        # 顶层评论：一行显示所有信息
        if level == 0:
            print(f"{indent}[{floor_number}] {user_info}: {comment['content']} ({time_info} {likes_info})")
        else:
            # 回复评论：一行显示
            # 如果是回复别人，显示被回复的用户（也带颜色）
            reply_to_info = ""
            if comment['reply_to_comment_id'] and comment['reply_to_nickname']:
                reply_to_nickname = comment['reply_to_nickname']
                reply_to_info = f"→@{Colors.CYAN}{reply_to_nickname}{Colors.RESET} "

            print(f"{indent}  ↳ {user_info} {reply_to_info}: {comment['content']} ({time_info} {likes_info})")

        # 递归打印该评论的回复（按热度排序）
        if comment['comment_id'] in replies_map:
            # 对回复也按热度排序
            sorted_replies = sorted(
                replies_map[comment['comment_id']],
                key=lambda x: x['likes_count'],
                reverse=True
            )
            for reply in sorted_replies:
                print_comment(reply, level + 1)

    # 打印所有顶层评论及其回复树
    for i, comment in enumerate(top_level_comments, 1):
        print_comment(comment, level=0, floor_number=i)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python show_all_comments.py <微博ID>")
        print("示例: python show_all_comments.py 5253489136775271")
        print()
        print("功能:")
        print("  - 展示指定微博的所有评论")
        print("  - 按热度（点赞数）降序排列")
        print("  - 支持楼层展示（回复会显示在被回复评论的下方）")
        print("  - 标注博主评论 🔥")
        sys.exit(1)

    mid = sys.argv[1]
    show_all_comments(mid)
