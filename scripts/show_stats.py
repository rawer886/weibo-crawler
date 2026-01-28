"""
数据统计查询脚本

用法:
    python scripts/show_stats.py                    # 查看数据库统计
    python scripts/show_stats.py --recent [N]      # 查看最近抓取的微博（默认10条）
    python scripts/show_stats.py --blogger <UID>   # 查看指定博主的抓取进度
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from display import show_db_status, show_recent_posts, show_blogger_status

USAGE = """用法: python scripts/show_stats.py [选项]

选项:
    (无参数)              查看数据库统计
    --recent [N]         查看最近抓取的微博（默认10条）
    --blogger <UID>      查看指定博主的抓取进度

示例:
    python scripts/show_stats.py
    python scripts/show_stats.py --recent
    python scripts/show_stats.py --recent 20
    python scripts/show_stats.py --blogger 1497035431"""


if __name__ == "__main__":
    args = sys.argv[1:]

    if '-h' in args or '--help' in args:
        print(USAGE)
        sys.exit(0)

    if '--recent' in args:
        idx = args.index('--recent')
        limit = 10
        if idx + 1 < len(args) and args[idx + 1].isdigit():
            limit = int(args[idx + 1])
        show_recent_posts(limit)
    elif '--blogger' in args:
        idx = args.index('--blogger')
        if idx + 1 >= len(args):
            print("错误: --blogger 需要指定 UID")
            print(USAGE)
            sys.exit(1)
        show_blogger_status(args[idx + 1])
    else:
        show_db_status()
