"""
展示指定博主的最近评论，支持分页浏览
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_blogger, get_blogger_comments
from display import display_blogger_header, display_blogger_comment


def show_blogger_comments(uid: str, page_size: int = 5):
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
    print(f"共 {total} 条评论（按时间倒序）")
    print(f"按回车键翻页（每页 {page_size} 条），Ctrl+C 退出")
    print()

    page = 0
    total_pages = (total + page_size - 1) // page_size

    while page < total_pages:
        start = page * page_size
        end = min(start + page_size, total)

        for i in range(start, end):
            display_blogger_comment(comments[i], i + 1, total)

        page += 1

        if page < total_pages:
            remaining = total - end
            try:
                input(f"\n--- 第 {page}/{total_pages} 页，还有 {remaining} 条，按回车继续 ---\n")
            except KeyboardInterrupt:
                print("\n\n已退出浏览")
                return

    print()
    print("已展示全部评论")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/show_blogger_replies.py <博主UID>")
        print("示例: python scripts/show_blogger_replies.py 1234567890")
        sys.exit(1)

    show_blogger_comments(sys.argv[1])
