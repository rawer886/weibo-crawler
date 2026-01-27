"""
输出展示模块

职责：
- 评论展示
- 统计信息展示
- 抓取结果展示
"""
from collections import defaultdict

from database import init_database, get_stats, get_recent_posts


# ANSI 颜色代码
class Colors:
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'


def display_comments(comments: list):
    """展示评论，按热度排序，支持楼层展示"""
    if not comments:
        print("没有找到评论")
        return

    comment_map = {c['comment_id']: c for c in comments if c.get('comment_id')}
    replies_map = defaultdict(list)
    top_level_comments = []

    for comment in comments:
        reply_to_id = comment.get('reply_to_comment_id')
        if reply_to_id and reply_to_id in comment_map:
            replies_map[reply_to_id].append(comment)
        else:
            top_level_comments.append(comment)

    top_level_comments.sort(key=lambda x: x.get('likes_count', 0), reverse=True)

    def print_comment(comment, level=0, floor_number=None):
        indent = "  " * level
        is_blogger = comment.get('is_blogger_reply', False)
        nickname = comment.get('nickname') or comment.get('uid') or '未知用户'

        if is_blogger:
            user_info = f"{Colors.YELLOW}{nickname}🔥{Colors.RESET}"
        else:
            user_info = f"{Colors.CYAN}{nickname}{Colors.RESET}"

        likes_info = f"👍 {comment.get('likes_count', 0)}"
        time_info = comment.get('created_at', '未知')

        if level == 0:
            print(f"{indent}[{floor_number}] {user_info}: {comment.get('content', '')} ({time_info} {likes_info})")
        else:
            reply_to_info = ""
            if comment.get('reply_to_nickname'):
                reply_to_info = f"→@{Colors.CYAN}{comment['reply_to_nickname']}{Colors.RESET} "
            print(f"{indent}  ↳ {user_info} {reply_to_info}: {comment.get('content', '')} ({time_info} {likes_info})")

        comment_id = comment.get('comment_id')
        if comment_id and comment_id in replies_map:
            sorted_replies = sorted(replies_map[comment_id], key=lambda x: x.get('likes_count', 0), reverse=True)
            for reply in sorted_replies:
                print_comment(reply, level + 1)

    for i, comment in enumerate(top_level_comments, 1):
        print_comment(comment, level=0, floor_number=i)


def print_crawl_stats(stats: dict):
    """打印抓取统计结果"""
    print("-" * 50)
    print("抓取完成:")
    print(f"  微博: {'已保存' if stats['post_saved'] else '已存在'}")
    print(f"  评论: 新增 {stats['comments_saved']} 条，更新 {stats['comments_updated']} 条")
    if stats['images_downloaded'] > 0:
        print(f"  微博图片: {stats['images_downloaded']} 张")
    if stats['comment_images_downloaded'] > 0:
        print(f"  评论图片: {stats['comment_images_downloaded']} 张")


def show_db_status():
    """显示数据库统计信息"""
    init_database()
    stats = get_stats()

    print("\n=== 数据库统计 ===")
    print(f"博主数量: {stats['bloggers_count']}")
    print(f"微博数量: {stats['posts_count']}")
    print(f"评论数量: {stats['comments_count']}")

    if stats['posts_by_blogger']:
        print("\n各博主微博数:")
        for uid, count in stats['posts_by_blogger'].items():
            print(f"  {uid}: {count} 条")


def show_recent_posts(limit: int = 10):
    """显示最近抓取的微博"""
    init_database()
    posts = get_recent_posts(limit)

    if not posts:
        print("暂无数据")
        return

    print("\n=== 最近抓取的微博 ===\n")
    for post in posts:
        nickname = post.get('nickname') or post['uid']
        content = post['content'] or "(无内容)"
        if len(content) > 100:
            content = content[:100] + "..."

        print(f"【{nickname}】{post['created_at']}")
        print(f"  {content}")
        print(f"  转发:{post['reposts_count']} 评论:{post['comments_count']} 点赞:{post['likes_count']}")
        print()
