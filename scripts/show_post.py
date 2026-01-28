"""
展示指定微博及其所有评论
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from display import display_post_with_comments

USAGE = """用法: python scripts/show_post.py <微博ID> [-b]

参数:
  -b, --blogger-only  只展示博主评论

示例:
  python scripts/show_post.py 5254891884513482
  python scripts/show_post.py 5254891884513482 -b"""


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or '-h' in args or '--help' in args:
        print(USAGE)
        sys.exit(0 if '-h' in args or '--help' in args else 1)

    mid = args[0]
    blogger_only = '-b' in args or '--blogger-only' in args
    display_post_with_comments(mid, blogger_only=blogger_only)
