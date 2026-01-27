"""
展示指定博主的最近评论，支持分页浏览
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_blogger, get_blogger_comments
from display import display_blogger_header, display_blogger_comment


def show_blogger_comments(uid: str):
    """展示指定博主的最近评论，支持分页浏览"""
    blogger = get_blogger(uid)

    if not blogger:
        print(f"未找到博主: {uid}")
        return

    display_blogger_header(blogger, uid)

    comments = get_blogger_comments(uid)

    if not comments:
        print("该博主没有评论记录")
        return

    total = len(comments)
    print(f"共找到 {total} 条评论，按时间倒序展示（最新在前）")
    print(f"首次展示 5 条，之后按回车键继续展示（每次1条）")
    print()

    # 分页展示：首次5条，之后每次1条
    first_batch_size = 5
    displayed = 0

    # 首次展示5条
    for i, comment in enumerate(comments[:first_batch_size], 1):
        display_blogger_comment(comment, i, total)

    displayed = min(first_batch_size, total)

    # 之后每次展示1条
    while displayed < total:
        remaining = total - displayed
        try:
            input(f"--- 还有 {remaining} 条评论，按回车键继续，Ctrl+C 退出 ---")
        except KeyboardInterrupt:
            print("\n\n已退出浏览")
            break

        comment = comments[displayed]
        displayed += 1
        display_blogger_comment(comment, displayed, total)

    if displayed >= total:
        print()
        print("已展示全部评论")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python show_blogger_comments.py <博主UID>")
        print("示例: python show_blogger_comments.py 1234567890")
        print()
        print("功能:")
        print("  - 输入博主UID，展示该博主的所有评论")
        print("  - 按时间倒序排列（最新评论在前）")
        print("  - 同时显示评论所属的微博正文（截断展示）")
        print("  - 首次展示5条，之后按回车键每次展示1条")
        sys.exit(1)

    uid = sys.argv[1]
    show_blogger_comments(uid)
