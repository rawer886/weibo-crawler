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
    DIM = '\033[2m'
    GRAY = '\033[90m'
    RESET = '\033[0m'


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本，如果超过最大长度则添加省略号"""
    if not text:
        return ""
    text = text.replace('\n', ' ').replace('\r', '')
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def display_post_header(post: dict):
    """展示微博信息头"""
    print("=" * 80)
    print(f"微博ID: {post['mid']}")
    blogger_name = post.get('blogger_nickname') or post.get('nickname') or post.get('uid')
    print(f"博主: {blogger_name}")
    print(f"发布时间: {post.get('created_at', '未知')}")
    content = post.get('content') or ''
    print(f"微博内容: {truncate_text(content, 100)}")
    print(f"点赞数: {post.get('likes_count', 0)} | 转发数: {post.get('reposts_count', 0)} | 评论数: {post.get('comments_count', 0)}")
    print("=" * 80)
    print()


def display_blogger_header(blogger: dict, uid: str):
    """展示博主信息头"""
    print("=" * 80)
    print(f"博主: {Colors.YELLOW}{blogger.get('nickname') or uid}{Colors.RESET}")
    print(f"UID: {uid}")
    print(f"粉丝数: {blogger.get('followers_count') or '未知'}")
    print("=" * 80)
    print()


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

        # 用户名：博主高亮黄色，普通用户浅灰色
        if is_blogger:
            user_info = f"{Colors.YELLOW}{nickname}🔥{Colors.RESET}"
        else:
            user_info = f"{Colors.GRAY}{nickname}{Colors.RESET}"

        likes_info = f"点赞数 {comment.get('likes_count', 0)}"
        time_info = comment.get('created_at', '未知')

        if level == 0:
            print(f"{indent}[{floor_number}] {user_info}: {comment.get('content', '')} {Colors.GRAY}({time_info} {likes_info}){Colors.RESET}")
        else:
            print(f"{indent}      ↳ {user_info}: {comment.get('content', '')} {Colors.GRAY}({time_info} {likes_info}){Colors.RESET}")

        comment_id = comment.get('comment_id')
        if comment_id and comment_id in replies_map:
            sorted_replies = sorted(replies_map[comment_id], key=lambda x: x.get('likes_count', 0), reverse=True)
            for reply in sorted_replies:
                print_comment(reply, level + 1)

    for i, comment in enumerate(top_level_comments, 1):
        print_comment(comment, level=0, floor_number=i)


def display_blogger_comment(comment: dict, index: int, total: int):
    """
    展示博主评论（含微博上下文）

    参数:
        comment: 评论数据（需包含 post_content, post_created_at 等字段）
        index: 当前索引（从1开始）
        total: 总数
    """
    print("-" * 80)

    post_content = truncate_text(comment.get('post_content', ''), 100)
    post_time = comment.get('post_created_at') or "未知"
    comment_time = comment.get('created_at') or "未知"
    likes_info = f"点赞数 {comment.get('likes_count', 0)}"

    print(f"[{index}/{total}] 微博ID: {comment['mid']}")
    print(f"  📝 {post_content} {Colors.DIM}[{post_time}]{Colors.RESET}")
    print(f"  💬 {Colors.YELLOW}{comment.get('content', '')}{Colors.RESET}  {Colors.DIM}{likes_info} [{comment_time}]{Colors.RESET}")

    if comment.get('reply_to_comment_id'):
        reply_to_nickname = comment.get('reply_to_nickname')
        reply_to_info = f"@{reply_to_nickname}" if reply_to_nickname else f"@{comment['reply_to_comment_id']}"

        if comment.get('reply_to_content'):
            reply_content = truncate_text(comment['reply_to_content'], 80)
            print(f"  {Colors.CYAN}↳ 回复 {reply_to_info}: {reply_content}{Colors.RESET}")
        else:
            print(f"  {Colors.CYAN}↳ 回复 {reply_to_info}{Colors.RESET}")


def print_crawl_stats(stats: dict, post: dict = None):
    """打印抓取统计结果"""
    print("-" * 50)
    print()
    print("抓取完成:")
    print(f"  微博: {'新增' if stats['post_saved'] else '已存在'}")

    # 展示微博正文和互动数据
    if post:
        content = truncate_text(post.get('content', ''), 80)
        if content:
            print(f"  正文: {Colors.CYAN}{content}{Colors.RESET}")
        images = post.get('images', [])
        if images:
            print(f"  图片: {len(images)} 张")
        reposts = post.get('reposts_count', 0)
        comments = post.get('comments_count', 0)
        likes = post.get('likes_count', 0)
        print(f"  互动: 点赞 {likes} | 转发 {reposts} | 评论 {comments}")

    if stats['images_downloaded'] > 0:
        print(f"  微博图片下载: {stats['images_downloaded']} 张")
    if stats['comment_images_downloaded'] > 0:
        print(f"  评论图片下载: {stats['comment_images_downloaded']} 张")


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
