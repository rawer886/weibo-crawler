"""
微博爬虫核心模块

职责：
- 协调各模块完成爬虫任务
- 单条微博抓取流程
- 博主批量抓取流程
"""
import os
import random
import signal
import time
from typing import Generator

from config import CRAWLER_CONFIG
from logger import setup_logging, get_logger
from database import (
    save_blogger, save_post, update_post, save_comment,
    is_post_exists, update_post_local_images, update_post_repost_local_images,
    update_comment_likes, get_blogger,
    save_post_from_list, get_posts_pending_detail, mark_post_detail_done,
    get_list_scan_oldest_mid, update_list_scan_oldest_mid
)
from browser import BrowserManager
from api import WeiboAPI
from parser import PageParser
from image import ImageDownloader
from display import display_post_with_comments, Colors

# 初始化日志
setup_logging()
logger = get_logger(__name__)

# 信号处理
_stopping = False


def _signal_handler(signum, frame):
    global _stopping
    if _stopping:
        print("\n强制退出...")
        os._exit(1)
    _stopping = True
    print("\n\n收到停止信号，正在关闭...")
    raise SystemExit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


class WeiboCrawler:
    """微博爬虫"""

    def __init__(self):
        self.browser = BrowserManager()
        self.api = WeiboAPI()
        self.parser = None  # 需要 page 初始化
        self.image_downloader = ImageDownloader()

    def start(self, url: str = None):
        """启动浏览器"""
        self.browser.start(url)
        self.parser = PageParser(self.browser.page)
        self.image_downloader.set_page(self.browser.page)

    def stop(self):
        """停止浏览器"""
        self.browser.stop()

    def login(self) -> bool:
        """登录"""
        result = self.browser.login()
        if result:
            self.api.set_cookies(self.browser.cookies_for_request)
        return result

    def check_login_status(self) -> bool:
        """检查登录状态"""
        result = self.browser.check_login_status()
        if result:
            self.api.set_cookies(self.browser.cookies_for_request)
        return result

    def parse_numeric_mid_from_page(self) -> str:
        """从当前页面解析数字 mid"""
        return self.parser.parse_numeric_mid()

    def crawl_single_post(self, uid: str, mid: str, source_url: str = None,
                         skip_navigation: bool = False, skip_blogger_check: bool = False,
                         show_comments: bool = True, stable_days: int = None) -> dict:
        """抓取单条微博

        参数:
            skip_navigation: 跳过页面导航（当页面已在目标位置时使用）
            skip_blogger_check: 跳过博主信息检查（批量抓取时已在入口处处理）
            show_comments: 展示评论（批量抓取时设为 False）
            stable_days: 如果提供，则发布时间在 stable_days 内的微博 detail_status 设为 0
        """
        result = {
            "post": None,
            "comments": [],
            "success": False,  # 微博是否成功处理（保存或已存在）
            "stats": {
                "post_saved": False,
                "comments_saved": 0,
                "comments_updated": 0,
                "images_downloaded": 0,
                "repost_images_downloaded": 0,
                "comment_images_downloaded": 0,
            }
        }

        # 如果没有传入 source_url，使用默认格式
        if source_url is None:
            source_url = f"https://weibo.com/{uid}/{mid}"

        # 1. 访问微博详情页（可跳过）
        if not skip_navigation:
            url = f"https://weibo.com/{uid}/{mid}"
            logger.info(f"访问微博详情页: {url}")
            self.browser.goto(url)
            time.sleep(5)

        # 2. 保存博主信息（仅在数据库中不存在时调用API）
        if not skip_blogger_check:
            self._ensure_blogger_exists(uid)

        # 3. 解析微博内容
        post = self.parser.parse_post(uid, mid, source_url=source_url)
        result["post"] = post

        # 4. 保存微博（有文本、图片、视频，或转发的原微博有内容即可保存）
        has_content = post and (
            post.get("content") or post.get("images") or post.get("video") or
            post.get("repost_content") or post.get("repost_images") or post.get("repost_video")
        )
        if has_content:
            is_new = save_post(post, stable_days=stable_days)
            if not is_new:
                # 已存在则更新内容
                update_post(post)
            result["stats"]["post_saved"] = is_new
            result["success"] = True  # 成功保存或已存在

            # 5. 下载微博图片
            if post.get("images"):
                local_paths = self.image_downloader.download_post_images(post)
                result["stats"]["images_downloaded"] = len(local_paths)
                if local_paths:
                    update_post_local_images(mid, local_paths)

            # 6. 下载原微博图片（如果是转发）
            if post.get("repost_images"):
                repost_local_paths = self.image_downloader.download_repost_images(post)
                result["stats"]["repost_images_downloaded"] = len(repost_local_paths)
                if repost_local_paths:
                    update_post_repost_local_images(mid, repost_local_paths)
        else:
            # 跳过保存时 success 保持 False，不会标记 detail_status 为已抓取
            logger.warning(f"微博无有效内容（无文本、图片或视频），跳过保存: {mid}")

        # 7. 抓取评论（评论数为 0 时跳过）
        comments_count = post.get("comments_count", 0) if post else 0
        if comments_count > 0:
            print()
            # 滚动并点击「按热度」
            if self._scroll_and_click_hot_button():
                time.sleep(2)

            logger.info("等待评论加载...")
            time.sleep(5)

            # 抓取评论（两轮）
            all_comments = {}
            comments, main_count = self.parser.parse_comments(mid, uid)
            for c in comments:
                if c.get("comment_id"):
                    all_comments[c["comment_id"]] = c
            logger.info(f"第 1 轮抓取: 获取 {len(comments)} 条评论, 其中 {main_count} 个主评论")

            # 滚动后再抓一轮
            if comments:
                viewport_height = self.browser.page.evaluate("() => window.innerHeight")
                scroll_distance = int(viewport_height * random.uniform(0.8, 1.0))
                self.browser.scroll_page(scroll_distance)
                time.sleep(random.uniform(2, 3))

                comments, main_count = self.parser.parse_comments(mid, uid)
                new_count = 0
                new_main_count = 0
                for c in comments:
                    cid = c.get("comment_id")
                    if cid and cid not in all_comments:
                        all_comments[cid] = c
                        new_count += 1
                        if not c.get("reply_to_comment_id"):
                            new_main_count += 1
                logger.info(f"第 2 轮抓取: 获取 {len(comments)} 条评论，其中新增 {new_count} 条，包含 {new_main_count} 条主评论")

            # 保存评论
            comments = list(all_comments.values())
            result["comments"] = comments

            for comment in comments:
                # 下载评论图片
                if comment.get("images"):
                    local_paths = self.image_downloader.download_comment_images(comment, uid)
                    if local_paths:
                        comment["local_images"] = local_paths
                        result["stats"]["comment_images_downloaded"] += len(local_paths)

                # 保存评论
                if save_comment(comment):
                    result["stats"]["comments_saved"] += 1
                else:
                    if update_comment_likes(comment["comment_id"], comment.get("likes_count", 0)):
                        result["stats"]["comments_updated"] += 1

            # 输出评论保存统计
            self._log_comment_stats(result["stats"])
        else:
            logger.info("评论数为 0，跳过评论抓取")

        # 8. 展示抓取结果（从数据库读取）
        print()
        logger.info("抓取完成")
        print()
        display_post_with_comments(mid, show_comments=show_comments)
        return result

    def crawl_blogger(self, uid: str, mode: str = "history"):
        """抓取博主微博

        参数:
            uid: 博主ID
            mode:
                - "history": 两阶段抓取（扫描列表 + 抓取详情）
                - "new": 抓取最新微博（stable_days 内，不使用缓存）
        """
        stable_days = CRAWLER_CONFIG.get("stable_days", 1)
        logger.info(f"开始抓取博主: {uid}, 模式: {mode}")

        # 确保博主信息已入库
        blogger_info = self._ensure_blogger_exists(uid)
        if not blogger_info:
            logger.error(f"无法获取博主信息: {uid}")
            return

        if mode == "history":
            # 历史模式：按需拉取列表 + 抓取详情
            self._crawl_pending_details(uid, stable_days)
            return

        # 新微博模式：不使用缓存，抓取到与历史数据衔接为止
        logger.info("=== 抓取最新微博 ===")

        consecutive_exists = 0
        max_consecutive = 5
        posts_processed = 0
        max_posts = CRAWLER_CONFIG.get("max_posts_per_run", 100)

        for post in self._iter_post_list(uid, cache_max_age=0):
            mid = post["mid"]

            if is_post_exists(mid):
                consecutive_exists += 1
                logger.debug(f"微博 {mid} 已存在 ({consecutive_exists}/{max_consecutive})")
                if consecutive_exists >= max_consecutive:
                    logger.info(f"连续 {max_consecutive} 条微博已存在，与历史数据衔接，停止")
                    break
                continue

            # 遇到新微博，重置计数
            consecutive_exists = 0
            posts_processed += 1

            logger.info(f"处理第 {posts_processed} 条新微博: {mid}")
            self.crawl_single_post(uid, mid, skip_blogger_check=True, show_comments=False,
                                   stable_days=stable_days)

            if posts_processed >= max_posts:
                logger.info(f"已达到单次最大抓取数 {max_posts}，停止")
                break

            self._random_delay()

        if posts_processed == 0:
            logger.info("没有新微博")
        else:
            logger.info(f"博主 {uid} 抓取完成，共处理 {posts_processed} 条新微博")

    def _iter_post_list(self, uid: str, since_id: str = None,
                        cache_max_age: float = None) -> Generator[dict, None, None]:
        """迭代获取微博列表（按需拉取）

        每次拉取一页，yield 单条微博，调用方决定何时停止
        """
        current_since_id = since_id
        page = 1

        while True:
            logger.info(f"获取第 {page} 页微博列表")
            posts, next_since_id, reached_cutoff = self.api.get_post_list(
                uid, since_id=current_since_id, max_count=20,
                check_date=True, cache_max_age=cache_max_age
            )

            if not posts:
                logger.info("没有更多微博")
                break

            for post in posts:
                yield post

            if reached_cutoff:
                logger.info("已到达时间边界")
                break

            if not next_since_id:
                logger.info("已到达最后一页")
                break

            current_since_id = next_since_id
            page += 1

    def _scan_post_list_batch(self, uid: str, batch_size: int = 20) -> int:
        """扫描一批微博列表并保存

        返回新增的微博数量
        """
        since_id = get_list_scan_oldest_mid(uid)

        posts, _, reached_cutoff = self.api.get_post_list(
            uid, since_id=since_id, max_count=batch_size, check_date=True
        )

        if not posts:
            return 0

        saved_count = 0
        oldest_mid = None
        for post in posts:
            oldest_mid = post["mid"]
            if save_post_from_list(post):
                saved_count += 1

        if oldest_mid:
            update_list_scan_oldest_mid(uid, oldest_mid)

        return saved_count

    def _crawl_pending_details(self, uid: str, stable_days: int):
        """抓取未抓详情的微博（detail_status=0 且超过 stable_days）

        按需拉取列表：当待抓队列不足时，拉取更多
        """
        print()
        print(f"{Colors.BLUE}=== 抓取微博详情 ==={Colors.RESET}")

        max_count = CRAWLER_CONFIG.get("max_posts_per_run", 50)
        min_queue_size = 5

        for processed in range(1, max_count + 1):
            # 获取待抓取的微博
            pending = get_posts_pending_detail(uid, stable_days, limit=min_queue_size + 5)

            # 队列为空或不足时，尝试补充
            if len(pending) < min_queue_size:
                new_count = self._scan_post_list_batch(uid)
                if new_count > 0:
                    logger.info(f"补充列表，新增 {new_count} 条")
                    pending = get_posts_pending_detail(uid, stable_days, limit=min_queue_size + 5)

            if not pending:
                logger.info("没有更多微博可抓取")
                break

            # 处理第一条待抓微博
            mid = pending[0]["mid"]
            logger.info(f"[{processed}/{max_count}] 抓取: {mid}")
            result = self.crawl_single_post(uid, mid, skip_blogger_check=True, show_comments=False)

            if result["success"]:
                mark_post_detail_done(mid)

            if processed < max_count:
                self._random_delay()

        logger.info(f"博主 {uid} 详情抓取完成")

    def _scroll_and_click_hot_button(self) -> bool:
        """滚动并点击「按热度」按钮"""
        try:
            hot_btn = self.browser.page.locator('text="按热度"').first

            if hot_btn.count() == 0:
                logger.info("未找到「按热度」按钮")
                return False

            logger.info("滚动到「按热度」按钮...")
            self.browser.smooth_scroll_to_element(hot_btn)

            try:
                hot_btn.wait_for(state="visible", timeout=3000)
                hot_btn.click()
                logger.info("已点击「按热度」按钮")
                self.browser.page.wait_for_load_state("networkidle", timeout=5000)
                return True
            except:
                logger.warning("按钮无法点击")
                return False

        except Exception as e:
            logger.warning(f"操作失败: {e}")
            return False

    def _ensure_blogger_exists(self, uid: str):
        """确保博主信息已入库"""
        blogger = get_blogger(uid)
        if blogger:
            logger.info(f"博主信息已入库: {blogger.get('nickname', uid)}")
            return blogger

        blogger_info = self.api.get_blogger_info(uid)
        if blogger_info:
            save_blogger(blogger_info)
            logger.info(f"博主信息入库: {blogger_info.get('nickname', uid)}")
        return blogger_info

    def _log_comment_stats(self, stats: dict):
        """输出评论保存统计日志"""
        parts = []
        if stats.get('comments_saved'):
            parts.append(f"新增 {stats['comments_saved']} 条")
        if stats.get('comments_updated'):
            parts.append(f"更新 {stats['comments_updated']} 条点赞")
        if stats.get('comment_images_downloaded'):
            parts.append(f"下载 {stats['comment_images_downloaded']} 张图片")
        if parts:
            logger.info(f"评论保存: {', '.join(parts)}")

    def _random_delay(self, base_delay: float = None):
        """随机延迟"""
        base = base_delay or CRAWLER_CONFIG["delay"]
        delay = random.uniform(base * 0.5, base * 1.5)
        logger.debug(f"等待 {delay:.1f} 秒...")
        time.sleep(delay)
