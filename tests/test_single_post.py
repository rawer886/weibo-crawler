"""
测试单条微博的评论抓取
"""
import sys
import os
import re
import logging

# 添加父目录到路径，以便导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict
from crawler import WeiboCrawler
from database import save_comment, save_post
from config import LOG_CONFIG

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_CONFIG["level"]),
    format=LOG_CONFIG["format"],
    handlers=[
        logging.FileHandler(LOG_CONFIG["file"], encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ANSI 颜色代码
class Colors:
    CYAN = '\033[96m'      # 青色 - 用于普通用户名
    YELLOW = '\033[93m'    # 黄色 - 用于博主名字
    RESET = '\033[0m'      # 重置颜色


def display_comments(comments: list):
    """展示评论，按热度排序，支持楼层展示

    参数:
        comments: 评论列表
    """
    if not comments:
        logger.warning("没有找到评论")
        return

    # 构建评论映射：comment_id -> comment
    comment_map = {c['comment_id']: c for c in comments if c.get('comment_id')}

    # 构建回复关系：被回复的评论ID -> [回复它的评论列表]
    replies_map = defaultdict(list)

    # 顶层评论列表（没有 reply_to_comment_id 或者被回复的评论不存在的）
    top_level_comments = []

    for comment in comments:
        reply_to_id = comment.get('reply_to_comment_id')
        if reply_to_id and reply_to_id in comment_map:
            replies_map[reply_to_id].append(comment)
        else:
            top_level_comments.append(comment)

    # 顶层评论按热度排序
    top_level_comments.sort(key=lambda x: x.get('likes_count', 0), reverse=True)

    def print_comment(comment, level=0, floor_number=None):
        """打印单条评论"""
        indent = "  " * level

        # 构建用户信息（带颜色）
        is_blogger = comment.get('is_blogger_reply', False)
        nickname = comment.get('nickname') or comment.get('uid') or '未知用户'

        if is_blogger:
            user_info = f"{Colors.YELLOW}{nickname}🔥{Colors.RESET}"
        else:
            user_info = f"{Colors.CYAN}{nickname}{Colors.RESET}"

        # 点赞和时间信息
        likes_info = f"👍 {comment.get('likes_count', 0)}"
        time_info = comment.get('created_at', '未知')

        # 顶层评论
        if level == 0:
            print(f"{indent}[{floor_number}] {user_info}: {comment.get('content', '')} ({time_info} {likes_info})")
        else:
            # 回复评论
            reply_to_info = ""
            if comment.get('reply_to_nickname'):
                reply_to_info = f"→@{Colors.CYAN}{comment['reply_to_nickname']}{Colors.RESET} "
            print(f"{indent}  ↳ {user_info} {reply_to_info}: {comment.get('content', '')} ({time_info} {likes_info})")

        # 递归打印回复（按热度排序）
        comment_id = comment.get('comment_id')
        if comment_id and comment_id in replies_map:
            sorted_replies = sorted(
                replies_map[comment_id],
                key=lambda x: x.get('likes_count', 0),
                reverse=True
            )
            for reply in sorted_replies:
                print_comment(reply, level + 1)

    # 打印所有顶层评论及其回复树
    for i, comment in enumerate(top_level_comments, 1):
        print_comment(comment, level=0, floor_number=i)


def build_url(url_or_uid: str, mid: str = None) -> str:
    """构建微博URL

    参数:
        url_or_uid: 微博URL或博主UID
        mid: 微博ID（当第一个参数是UID时需要）

    返回:
        完整的微博URL
    """
    if mid is None:
        # 已经是URL
        return url_or_uid
    else:
        # uid + mid 模式，拼接URL
        return f"https://weibo.com/{url_or_uid}/{mid}"


def is_numeric_mid(url: str) -> bool:
    """判断URL中的mid是否为数字格式"""
    match = re.search(r'weibo\.com/\d+/(\w+)', url)
    if match:
        mid_part = match.group(1)
        return mid_part.isdigit()
    return False


def parse_uid_mid_from_url(url: str) -> tuple[str, str]:
    """从URL字符串中解析uid和mid"""
    match = re.search(r'weibo\.com/(\d+)/(\w+)', url)
    if match:
        return match.group(1), match.group(2)
    raise ValueError(f"无法从URL解析uid和mid: {url}")


def parse_numeric_mid_from_dom(crawler) -> str:
    """从已加载的页面DOM中解析数字格式的mid

    返回:
        数字格式的mid
    """
    dom_data = crawler.page.evaluate("""
        () => {
            // 方法1: 从 header 标签获取 (详情页结构)
            const header = document.querySelector('header[id][userinfo]');
            if (header) {
                const mid = header.getAttribute('id');
                if (mid && /^\\d+$/.test(mid)) {
                    return { mid };
                }
            }

            // 方法2: 从任意带 mid 属性的元素获取
            const weiboItem = document.querySelector('[mid]');
            if (weiboItem) {
                const mid = weiboItem.getAttribute('mid');
                return { mid };
            }

            return null;
        }
    """)

    if dom_data and dom_data.get('mid'):
        return dom_data['mid']

    raise ValueError("无法从DOM解析数字mid")


def test_single_post_comments(url_or_uid: str, mid: str = None):
    """测试单条微博的评论抓取

    参数:
        url_or_uid: 微博URL或博主UID
        mid: 微博ID（当第一个参数是UID时需要）
    """
    crawler = WeiboCrawler()

    try:
        import time

        # === 1. 访问页面 ===
        url = build_url(url_or_uid, mid)
        logger.info(f"访问微博页面: {url}")
        crawler.start(url)
        logger.info("等待5秒让页面完全加载...")
        time.sleep(5)
        print()  # 空行分隔

        # 检查登录状态
        if not crawler.check_login_status():
            logger.warning("需要登录...")
            if not crawler.login():
                logger.error("登录失败")
                return

        # 从URL解析uid和mid
        uid, mid_from_url = parse_uid_mid_from_url(url)
        if is_numeric_mid(url):
            numeric_mid = mid_from_url
            logger.info(f"UID: {uid}, MID: {numeric_mid}")
        else:
            logger.info(f"检测到密文mid: {mid_from_url}，从页面解析数字mid...")
            try:
                numeric_mid = parse_numeric_mid_from_dom(crawler)
                logger.info(f"UID: {uid}, MID: {numeric_mid} (从DOM解析)")
            except ValueError as e:
                logger.error(f"解析失败: {e}")
                print("\n" + "=" * 80)
                input("按回车键退出浏览器...")
                return

        # === 2. 抓取微博正文 ===
        print()  # 空行分隔
        logger.info("开始抓取微博内容...")
        post = crawler.parse_post_from_detail_page(uid, numeric_mid)
        if post:
            from database import update_post
            if update_post(post):
                logger.info(f"微博数据已更新到数据库: {numeric_mid} (内容长度={len(post.get('content', ''))}, 点赞={post.get('likes_count', 0)})")
            elif save_post(post):
                logger.info(f"微博已保存到数据库: {numeric_mid}")
        else:
            logger.warning("无法解析微博信息，仅抓取评论")

        # === 3. 滑动页面，点击「按热度」按钮 ===
        print()  # 空行分隔
        if crawler._scroll_and_wait_for_hot_button():
            time.sleep(2)
            crawler._click_hot_sort_button(scroll_first=False)
        else:
            logger.warning("未找到「按热度」按钮，直接抓取评论")

        # === 4. 抓取评论 ===
        logger.info("等待5秒让评论加载完成...")
        time.sleep(5)
        print()  # 空行分隔
        logger.info(f"开始抓取微博 {numeric_mid} 的评论...")
        comments = crawler.get_comments(uid, numeric_mid, click_hot_button=False)

        # 保存评论（新增或更新点赞数）
        from database import update_comment_likes
        saved_count = 0
        updated_count = 0
        for comment in comments:
            if save_comment(comment):
                saved_count += 1
            else:
                if update_comment_likes(comment["comment_id"], comment.get("likes_count", 0)):
                    updated_count += 1

        logger.info(f"新增 {saved_count} 条评论，更新 {updated_count} 条评论的点赞数")

        # 展示评论（按热度排序，支持楼层展示）
        print("\n" + "=" * 80)
        print(f"评论列表（按热度排序）：")
        print("=" * 80)
        display_comments(comments)

        # 等待用户确认后再退出
        print("\n" + "=" * 80)
        input("按回车键退出浏览器...")

    finally:
        crawler.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("参数输入错误！")
        print("\n用法: python tests/test_single_post.py <url>")
        print("      python tests/test_single_post.py <uid> <mid>")
        print("示例: python tests/test_single_post.py https://weibo.com/2014433131/QoTF4tv2X")
        print("      python tests/test_single_post.py https://weibo.com/1497035431/5256534089008730")
        print("      python tests/test_single_post.py 2014433131 5253489136775271")
        sys.exit(1)

    if len(sys.argv) == 2:
        test_single_post_comments(sys.argv[1])
    else:
        test_single_post_comments(sys.argv[1], sys.argv[2])
