"""
输出展示模块

职责：
- 评论展示
- 统计信息展示
- 抓取结果展示
"""
from collections import defaultdict

from .database import init_database, get_stats, get_recent_posts


# ANSI 颜色代码
class Colors:
    RED = '\033[91m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
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


def format_comment_content(comment: dict) -> str:
    """格式化评论内容，包含图片标记"""
    content = comment.get('content', '')
    if comment.get('images'):
        content += f' {Colors.CYAN}[图片]{Colors.RESET}'
    return content


def format_user_name(comment: dict) -> str:
    """格式化用户名，博主高亮"""
    is_blogger = comment.get('is_blogger_reply', False)
    nickname = comment.get('nickname') or comment.get('uid') or '未知用户'
    if is_blogger:
        return f"{Colors.YELLOW}{nickname}🔥{Colors.RESET}"
    return f"{Colors.GRAY}{nickname}{Colors.RESET}"


def format_comment_meta(comment: dict) -> str:
    """格式化评论元信息（时间、点赞）"""
    time_info = comment.get('created_at', '未知')
    likes_info = f"点赞数 {comment.get('likes_count', 0)}"
    return f"{Colors.GRAY}({time_info} {likes_info}){Colors.RESET}"


def print_single_comment(comment: dict, prefix: str = ""):
    """打印单条评论（基础方法）"""
    user = format_user_name(comment)
    content = format_comment_content(comment)
    meta = format_comment_meta(comment)
    print(f"{prefix}{user}: {content} {meta}")


# ==================== 微博展示 ====================

def display_post_header(post: dict):
    """展示微博信息头"""
    print("=" * 80)
    print(f"微博ID: {post['mid']}")
    print(f"博主UID: {post.get('uid')}")
    blogger_name = post.get('blogger_nickname') or post.get('nickname') or ''
    print(f"博主昵称: {Colors.YELLOW}{blogger_name}{Colors.RESET}")
    print(f"发布时间: {post.get('created_at', '未知')}")
    content = truncate_text(post.get('content', ''), 100)
    print(f"微博内容: {Colors.CYAN}{content}{Colors.RESET}")
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


# ==================== 评论展示 ====================

def display_comments(comments: list):
    """展示评论列表，按热度排序，支持楼层展示"""
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

    def print_comment_tree(comment, level=0, floor_number=None):
        if level == 0:
            prefix = f"[{floor_number}] "
        else:
            prefix = "  " * level + "      ↳ "

        print_single_comment(comment, prefix)

        comment_id = comment.get('comment_id')
        if comment_id and comment_id in replies_map:
            sorted_replies = sorted(replies_map[comment_id], key=lambda x: x.get('likes_count', 0), reverse=True)
            for reply in sorted_replies:
                print_comment_tree(reply, level + 1)

    for i, comment in enumerate(top_level_comments, 1):
        print_comment_tree(comment, level=0, floor_number=i)


def display_blogger_comment(comment: dict, index: int, total: int):
    """展示博主评论（含微博上下文）"""
    print("-" * 80)

    post_content = truncate_text(comment.get('post_content', ''), 100)
    post_time = comment.get('post_created_at') or "未知"
    content = format_comment_content(comment)
    meta = format_comment_meta(comment)

    print(f"[{index}/{total}] 微博ID: {comment['mid']}")
    print(f"  📝 {post_content} {Colors.DIM}[{post_time}]{Colors.RESET}")
    print(f"  💬 {Colors.YELLOW}{content}{Colors.RESET}  {meta}")

    if comment.get('reply_to_comment_id'):
        reply_to_nickname = comment.get('reply_to_nickname')
        reply_to_info = f"@{reply_to_nickname}" if reply_to_nickname else f"@{comment['reply_to_comment_id']}"

        if comment.get('reply_to_content'):
            reply_content = truncate_text(comment['reply_to_content'], 80)
            print(f"  {Colors.CYAN}↳ 回复 {reply_to_info}: {reply_content}{Colors.RESET}")
        else:
            print(f"  {Colors.CYAN}↳ 回复 {reply_to_info}{Colors.RESET}")


# ==================== 抓取结果展示 ====================

def display_post_with_comments(mid: str, blogger_only: bool = False, show_comments: bool = True):
    """展示微博及评论（从数据库读取）

    参数:
        mid: 微博ID
        blogger_only: 只展示博主评论
        show_comments: 是否展示评论
    """
    from .database import get_post_with_blogger, get_comments_by_mid

    post = get_post_with_blogger(mid)
    if not post:
        print(f"未找到微博: {mid}")
        return

    display_post_header(post)

    if not show_comments:
        return

    comments = get_comments_by_mid(mid, blogger_only=blogger_only)
    if not comments:
        print("该微博下没有博主评论" if blogger_only else "该微博下没有评论")
        return

    label = "博主评论" if blogger_only else "评论"
    print(f"共 {len(comments)} 条{label}（按热度排序）：")
    print()
    display_comments(comments)


# ==================== 数据库统计 ====================

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
        content = truncate_text(post.get('content', ''), 100)

        print(f"【{nickname}】{post['created_at']}")
        print(f"  {content}")
        print(f"  转发:{post['reposts_count']} 评论:{post['comments_count']} 点赞:{post['likes_count']}")
        print()


def show_blogger_status(uid: str):
    """显示博主抓取进度和数据统计"""
    from .database import get_blogger_stats

    init_database()
    stats = get_blogger_stats(uid)

    if not stats:
        print(f"未找到博主: {uid}")
        return

    blogger = stats["blogger"]
    posts = stats["posts"]
    comments = stats["comments"]
    progress = stats["progress"]

    print()
    print("=" * 60)
    print(f"博主: {Colors.YELLOW}{blogger.get('nickname') or uid}{Colors.RESET}")
    print(f"UID: {uid}")
    print(f"粉丝数: {blogger.get('followers_count') or '未知'}")
    print("=" * 60)

    print()
    print("--- 微博统计 ---")
    total = posts.get("total", 0)
    pending = posts.get("pending_detail", 0)
    done = posts.get("detail_done", 0)
    print(f"总数: {total} 条")
    print(f"  已抓详情: {done} 条")
    print(f"  待抓详情: {pending} 条")
    if posts.get("oldest_post_time"):
        print(f"时间范围: {posts['oldest_post_time']} ~ {posts['newest_post_time']}")

    print()
    print("--- 评论统计 ---")
    print(f"总数: {comments.get('total', 0)} 条")
    print(f"博主回复: {comments.get('blogger_replies', 0)} 条")

    print()
    print("--- 抓取进度 ---")
    if progress:
        print(f"列表扫描位置: {progress.get('list_scan_oldest_mid') or '未开始'}")
        print(f"最后更新: {progress.get('updated_at') or '未知'}")
    else:
        print("尚未开始抓取")
    print()
