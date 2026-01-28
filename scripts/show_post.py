"""
展示指定微博及其所有评论
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_post_with_blogger, get_comments_by_mid
from display import display_post_header, display_comments


def show_post(mid: str, blogger_only: bool = False):
    """展示指定微博及其所有评论"""
    post = get_post_with_blogger(mid)

    if not post:
        print(f"未找到微博: {mid}")
        return

    display_post_header(post)

    comments = get_comments_by_mid(mid, blogger_only=blogger_only)

    if not comments:
        msg = "该微博下没有博主评论" if blogger_only else "该微博下没有评论"
        print(msg)
        return

    label = "博主评论" if blogger_only else "评论"
    print(f"共 {len(comments)} 条{label}（按热度排序）：")
    print()

    display_comments(comments)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help']:
        print("用法: python scripts/show_post.py <微博ID> [-b]")
        print("参数:")
        print("  -b, --blogger-only  只展示博主评论")
        print()
        print("示例:")
        print("  python scripts/show_post.py 5254891884513482")
        print("  python scripts/show_post.py 5254891884513482 -b")
        sys.exit(0 if '-h' in sys.argv or '--help' in sys.argv else 1)

    mid = sys.argv[1]
    blogger_only = '-b' in sys.argv or '--blogger-only' in sys.argv
    show_post(mid, blogger_only=blogger_only)
