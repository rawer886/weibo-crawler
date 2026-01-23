"""
微博爬虫核心模块
- 使用移动端 API 获取微博列表（支持 since_id 分页）
- 使用 Playwright 登录和获取详情页（全文+评论）
"""
import hashlib
import html
import json
import logging
import os
import random
import re
import signal
import sys
import time
import requests
from datetime import datetime
from typing import Optional, List, Tuple


# 全局变量，用于优雅停止
_crawler_instance = None
_stopping = False


def _signal_handler(signum, frame):
    """处理 Ctrl+C 信号"""
    global _stopping
    if _stopping:
        # 第二次 Ctrl+C，强制退出
        print("\n强制退出...")
        os._exit(1)

    _stopping = True
    print("\n\n⚠️  收到停止信号，正在关闭浏览器... (再按一次强制退出)")
    # 直接强制退出，让操作系统清理资源
    os._exit(0)


# 注册信号处理
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

from playwright.sync_api import sync_playwright, Page, Browser

from config import CRAWLER_CONFIG, LOG_CONFIG
from database import (
    save_blogger, save_post, save_comment,
    is_post_exists, init_database,
    get_blogger_oldest_mid, get_blogger_newest_mid,
    update_crawl_progress, get_crawl_progress,
    get_post_comment_count, update_post_local_images
)


class APICache:
    """API 响应持久化缓存（微博历史数据不会变，永久缓存）"""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _get_cache_path(self, key: str) -> str:
        """生成缓存文件路径"""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}.json")

    def get(self, key: str) -> Optional[dict]:
        """获取缓存，不存在返回 None（永久有效，不过期）"""
        cache_path = self._get_cache_path(key)

        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            return cached.get("data")
        except Exception:
            return None

    def set(self, key: str, data: dict):
        """设置缓存（持久化存储）"""
        cache_path = self._get_cache_path(key)

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({
                    "_cached_at": time.time(),
                    "data": data
                }, f, ensure_ascii=False)
        except Exception as e:
            logging.warning(f"缓存写入失败: {e}")

    def clear(self, uid: str = None):
        """清除缓存"""
        try:
            for f in os.listdir(self.cache_dir):
                if f.endswith(".json"):
                    os.remove(os.path.join(self.cache_dir, f))
        except Exception as e:
            logging.warning(f"清除缓存失败: {e}")

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


class WeiboCrawler:
    """微博爬虫类"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.is_logged_in = False
        self.cookies_for_request = {}  # 用于 requests 库的 cookies
        self.cache = APICache(
            cache_dir=CRAWLER_CONFIG.get("cache_dir", "cache")
        )

    def _random_delay(self, min_delay: float = None, max_delay: float = None):
        """随机延迟，模拟人类行为"""
        min_d = min_delay or CRAWLER_CONFIG["min_delay"]
        max_d = max_delay or CRAWLER_CONFIG["max_delay"]
        delay = random.uniform(min_d, max_d)
        logger.debug(f"等待 {delay:.1f} 秒...")
        time.sleep(delay)

    def download_images(self, post: dict) -> list:
        """
        下载微博图片到本地（优先从浏览器缓存获取）

        目录结构: images/{uid}/{YYYY-MM-DD}/{mid}_{index}.jpg

        返回: 本地文件路径列表
        """
        if not CRAWLER_CONFIG.get("download_images", False):
            return []

        images = post.get("images", [])
        if not images:
            return []

        uid = post["uid"]
        mid = post["mid"]
        created_at = post.get("created_at", "")

        # 解析日期，用于创建目录
        try:
            if "T" in created_at:
                date_str = created_at.split("T")[0]
            elif " " in created_at:
                date_str = created_at.split(" ")[0]
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
        except:
            date_str = datetime.now().strftime("%Y-%m-%d")

        # 创建目录: images/{uid}/{date}/
        save_dir = os.path.join(
            CRAWLER_CONFIG.get("images_dir", "images"),
            uid,
            date_str
        )
        os.makedirs(save_dir, exist_ok=True)

        local_paths = []

        for i, img_url in enumerate(images):
            try:
                ext = ".jpg"
                if ".png" in img_url.lower():
                    ext = ".png"
                elif ".gif" in img_url.lower():
                    ext = ".gif"
                elif ".webp" in img_url.lower():
                    ext = ".webp"

                filename = f"{mid}_{i+1}{ext}"
                filepath = os.path.join(save_dir, filename)

                if os.path.exists(filepath):
                    logger.debug(f"图片已存在: {filename}")
                    local_paths.append(filepath)
                    continue

                # 尝试从浏览器获取图片
                img_data = self._get_image_from_browser(img_url)

                if img_data:
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    local_paths.append(filepath)
                    logger.debug(f"图片已保存（浏览器缓存）: {filename}")
                else:
                    # 回退到 HTTP 请求
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Referer": "https://weibo.com/"
                    }
                    resp = requests.get(img_url, headers=headers, timeout=30)
                    if resp.status_code == 200:
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                        local_paths.append(filepath)
                        logger.debug(f"图片已保存（HTTP）: {filename}")

            except Exception as e:
                logger.warning(f"下载图片失败: {e}")

        if local_paths:
            logger.info(f"下载了 {len(local_paths)} 张图片到 {save_dir}")

        return local_paths

    def _get_image_from_browser(self, img_url: str) -> Optional[bytes]:
        """从浏览器获取已加载的图片数据"""
        import base64

        try:
            # 通过 JavaScript 从浏览器获取图片
            js_code = """
            (url) => {
                return new Promise((resolve) => {
                    const img = new Image();
                    img.crossOrigin = 'anonymous';
                    img.onload = () => {
                        const canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth;
                        canvas.height = img.naturalHeight;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0);
                        try {
                            const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
                            resolve(dataUrl);
                        } catch(e) {
                            resolve(null);
                        }
                    };
                    img.onerror = () => resolve(null);
                    img.src = url;
                    // 超时处理
                    setTimeout(() => resolve(null), 5000);
                });
            }
            """
            result = self.page.evaluate(js_code, img_url)

            if result and result.startswith('data:image'):
                # 解析 base64 数据
                base64_data = result.split(',')[1]
                return base64.b64decode(base64_data)

        except Exception as e:
            logger.debug(f"从浏览器获取图片失败: {e}")

        return None

    def start(self):
        """启动浏览器"""
        logger.info("启动浏览器...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=CRAWLER_CONFIG["headless"]
        )
        self.page = self.browser.new_page()

        # 设置更真实的 User-Agent
        self.page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        # 尝试加载已保存的 cookies
        self._load_cookies()

    def stop(self):
        """关闭浏览器"""
        logger.info("关闭浏览器...")
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _save_cookies(self):
        """保存 cookies 到文件"""
        cookies = self.page.context.cookies()
        with open(CRAWLER_CONFIG["cookie_file"], "w") as f:
            json.dump(cookies, f)
        self._update_request_cookies(cookies)
        logger.info("Cookies 已保存")

    def _load_cookies(self):
        """从文件加载 cookies"""
        try:
            with open(CRAWLER_CONFIG["cookie_file"], "r") as f:
                cookies = json.load(f)
            self.page.context.add_cookies(cookies)
            self._update_request_cookies(cookies)
            logger.info("Cookies 已加载")
            return True
        except FileNotFoundError:
            logger.info("未找到 cookies 文件，需要登录")
            return False
        except Exception as e:
            logger.warning(f"加载 cookies 失败: {e}")
            return False

    def _update_request_cookies(self, cookies: list):
        """将 Playwright cookies 转换为 requests 可用的格式"""
        self.cookies_for_request = {c["name"]: c["value"] for c in cookies}

    def login(self):
        """登录微博（手动登录）"""
        logger.info("正在打开微博登录页面...")
        self.page.goto("https://weibo.com/login.php")

        print("\n" + "=" * 50)
        print("请在浏览器中手动登录微博")
        print("登录成功后，按 Enter 键继续...")
        print("=" * 50 + "\n")

        input()

        # 验证登录状态
        self.page.goto("https://weibo.com")
        self._random_delay(2, 3)

        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
            if "login" not in self.page.url.lower():
                self.is_logged_in = True
                self._save_cookies()
                logger.info("登录成功！")
                return True
        except Exception as e:
            logger.debug(f"检查登录状态时出错: {e}")

        logger.warning("无法确认登录状态，请确保已登录")
        return False

    def check_login_status(self) -> bool:
        """检查当前登录状态"""
        logger.info("检查登录状态...")
        self.page.goto("https://weibo.com")
        self._random_delay(2, 3)

        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
            if "login" in self.page.url.lower() or "passport" in self.page.url.lower():
                self.is_logged_in = False
                return False
            self.is_logged_in = True
            return True
        except Exception as e:
            logger.warning(f"检查登录状态失败: {e}")
            return False

    def get_blogger_info(self, uid: str) -> Optional[dict]:
        """获取博主信息（通过移动端API，带缓存）"""
        logger.info(f"获取博主信息: {uid}")

        # 博主信息缓存（7天有效，博主信息变化不频繁）
        cache_key = f"blogger_{uid}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info(f"使用缓存的博主信息: {uid}")
            blogger_info = cached
            save_blogger(blogger_info)  # 同步到数据库
            return blogger_info

        url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
            "Referer": f"https://m.weibo.cn/u/{uid}"
        }

        try:
            resp = requests.get(url, headers=headers, cookies=self.cookies_for_request, timeout=10)
            data = resp.json()

            if data.get("ok") == 1:
                user_info = data.get("data", {}).get("userInfo", {})
                blogger_info = {
                    "uid": uid,
                    "nickname": user_info.get("screen_name", f"用户{uid}"),
                    "description": user_info.get("description", ""),
                    "followers_count": user_info.get("followers_count", 0),
                }
                save_blogger(blogger_info)
                self.cache.set(cache_key, blogger_info)  # 缓存博主信息
                logger.info(f"博主信息: {blogger_info['nickname']} (粉丝: {blogger_info['followers_count']})")
                return blogger_info
        except Exception as e:
            logger.error(f"获取博主信息失败: {e}")

        return None

    def _fetch_api_with_cache(self, url: str, cache_key: str, use_cache: bool = True) -> Optional[dict]:
        """
        带缓存的 API 请求

        参数:
            url: 请求地址
            cache_key: 缓存键
            use_cache: 是否使用缓存（第一页不缓存，需要检查新微博）
        """
        # 尝试从缓存获取（仅当 use_cache=True 时）
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info(f"命中缓存: {cache_key}")
                return cached

        # 缓存未命中或不使用缓存，发起请求
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
            "Referer": "https://m.weibo.cn/"
        }

        try:
            resp = requests.get(url, headers=headers, cookies=self.cookies_for_request, timeout=10)
            data = resp.json()

            # 请求成功且允许缓存时，保存到缓存
            if data.get("ok") == 1 and use_cache:
                self.cache.set(cache_key, data)
                logger.debug(f"已缓存: {cache_key}")

            return data
        except Exception as e:
            logger.error(f"API 请求失败: {e}")
            return None

    def get_post_list_via_api(self, uid: str, since_id: str = None, max_count: int = None, check_date: bool = False) -> Tuple[List[dict], str, bool]:
        """
        通过移动端 API 获取微博列表

        参数:
            uid: 博主ID
            since_id: 从这条微博之后开始获取（用于向后翻页）
            max_count: 最多获取多少条
            check_date: 是否检查时间范围（超出范围停止）

        返回:
            (微博列表, 下一页的since_id, 是否因超时间范围而停止)
        """
        max_count = max_count or CRAWLER_CONFIG.get("max_posts_per_run", 50)
        max_days = CRAWLER_CONFIG.get("max_days", 180)
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=max_days)
        container_id = f"107603{uid}"

        posts = []
        current_since_id = since_id
        page = 1
        reached_cutoff = False  # 是否到达时间截止点

        while len(posts) < max_count:
            url = f"https://m.weibo.cn/api/container/getIndex?containerid={container_id}"
            if current_since_id:
                url += f"&since_id={current_since_id}"

            # 缓存策略：
            # - 第一页（since_id=None）不缓存，需要检查新微博
            # - 历史页（since_id有值）永久缓存，历史数据不会变
            is_first_page = current_since_id is None
            cache_key = f"posts_{uid}_{current_since_id or 'first'}"

            try:
                logger.info(f"获取第 {page} 页微博列表..." + (" (不缓存)" if is_first_page else ""))
                data = self._fetch_api_with_cache(url, cache_key, use_cache=not is_first_page)

                if not data:
                    break

                if data.get("ok") != 1:
                    logger.warning(f"API 返回错误: {data}")
                    break

                cards = data.get("data", {}).get("cards", [])
                if not cards:
                    logger.info("没有更多微博了")
                    break

                for card in cards:
                    if card.get("card_type") != 9:  # 只处理微博卡片
                        continue

                    mblog = card.get("mblog", {})
                    mid = mblog.get("id") or mblog.get("mid")

                    if not mid:
                        continue

                    # 解析微博基础信息
                    post = {
                        "mid": str(mid),
                        "uid": uid,
                        "content": self._clean_html(mblog.get("text", "")),
                        "created_at": self._parse_weibo_time(mblog.get("created_at", "")),
                        "reposts_count": mblog.get("reposts_count", 0),
                        "comments_count": mblog.get("comments_count", 0),
                        "likes_count": mblog.get("attitudes_count", 0),
                        "is_repost": mblog.get("retweeted_status") is not None,
                        "repost_content": None,
                        "images": [],
                        "video_url": None,
                        "source_url": f"https://weibo.com/{uid}/{mid}",
                        "is_long_text": mblog.get("isLongText", False),  # 标记是否需要获取全文
                    }

                    # 转发内容
                    if post["is_repost"] and mblog.get("retweeted_status"):
                        rt = mblog["retweeted_status"]
                        post["repost_content"] = self._clean_html(rt.get("text", ""))
                        # 原微博博主信息
                        rt_user = rt.get("user", {})
                        if rt_user:
                            post["repost_uid"] = str(rt_user.get("id", ""))
                            post["repost_nickname"] = rt_user.get("screen_name", "")

                    # 图片
                    pics = mblog.get("pics", [])
                    for pic in pics:
                        large_url = pic.get("large", {}).get("url") or pic.get("url")
                        if large_url:
                            post["images"].append(large_url)

                    # 检查时间范围
                    if check_date and post["created_at"]:
                        try:
                            post_date = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                            if post_date.replace(tzinfo=None) < cutoff_date:
                                logger.info(f"微博 {mid} 已超出 {max_days} 天范围，停止抓取")
                                reached_cutoff = True
                                break
                        except:
                            pass

                    posts.append(post)

                    if len(posts) >= max_count:
                        break

                if reached_cutoff:
                    break

                # 获取下一页的 since_id
                card_info = data.get("data", {}).get("cardlistInfo", {})
                current_since_id = card_info.get("since_id")

                if not current_since_id:
                    logger.info("已到达最后一页")
                    break

                page += 1
                self._random_delay(1, 2)

            except Exception as e:
                logger.error(f"获取微博列表失败: {e}")
                break

        logger.info(f"共获取 {len(posts)} 条微博")
        return posts, current_since_id, reached_cutoff

    def _clean_html(self, html_text: str) -> str:
        """清理 HTML 标签，提取纯文本"""
        if not html_text:
            return ""
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', '', html_text)
        # 使用标准库解码所有 HTML 实体（&nbsp; &lt; &gt; &amp; &#xxx; &#xXXX; 等）
        text = html.unescape(text)
        # 清理多余空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _parse_weibo_time(self, time_str: str) -> str:
        """解析微博时间字符串"""
        if not time_str:
            return ""

        now = datetime.now()

        try:
            # "刚刚"
            if "刚刚" in time_str:
                return now.isoformat()

            # "X分钟前"
            match = re.search(r'(\d+)\s*分钟前', time_str)
            if match:
                from datetime import timedelta
                minutes = int(match.group(1))
                return (now - timedelta(minutes=minutes)).isoformat()

            # "X小时前"
            match = re.search(r'(\d+)\s*小时前', time_str)
            if match:
                from datetime import timedelta
                hours = int(match.group(1))
                return (now - timedelta(hours=hours)).isoformat()

            # "昨天 HH:MM"
            match = re.search(r'昨天\s*(\d{1,2}):(\d{2})', time_str)
            if match:
                from datetime import timedelta
                hour, minute = int(match.group(1)), int(match.group(2))
                yesterday = now - timedelta(days=1)
                return yesterday.replace(hour=hour, minute=minute, second=0).isoformat()

            # "MM-DD" (今年)
            match = re.match(r'^(\d{1,2})-(\d{1,2})$', time_str.strip())
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                return now.replace(month=month, day=day, hour=0, minute=0, second=0).isoformat()

            # 完整格式 "Wed Jan 22 12:34:56 +0800 2025"
            try:
                dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
                return dt.isoformat()
            except:
                pass

            return time_str
        except Exception as e:
            logger.debug(f"解析时间失败: {time_str}, {e}")
            return time_str

    def get_post_full_text(self, uid: str, mid: str) -> Optional[str]:
        """通过详情页获取微博全文（处理折叠情况）"""
        logger.debug(f"获取微博全文: {mid}")

        url = f"https://weibo.com/{uid}/{mid}"
        self.page.goto(url)
        self._random_delay(2, 3)

        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)

            # 尝试点击"展开全文"
            try:
                expand_btn = self.page.locator('text="展开"').first
                if expand_btn.count() > 0:
                    expand_btn.click()
                    self._random_delay(1, 2)
            except:
                pass

            # 获取正文
            content_selectors = [
                '[class*="detail_wbtext"]',
                '[class*="Feed_body"] [class*="wbpro-feed-content"]',
                '[class*="WB_text"]',
                '[class*="weibo-text"]',
            ]

            for selector in content_selectors:
                try:
                    elem = self.page.locator(selector).first
                    if elem.count() > 0:
                        content = elem.text_content().strip()
                        if content:
                            return content
                except:
                    continue

        except Exception as e:
            logger.warning(f"获取微博全文失败: {e}")

        return None

    def get_comments(self, uid: str, mid: str, target_count: int = None) -> list:
        """
        获取微博评论

        参数:
            uid: 博主ID
            mid: 微博ID
            target_count: 期望获取的评论数量（用于控制是否翻页）
                         如果一次返回的数据超过这个数量，会全部存储

        原则：不浪费已返回的数据
        """
        target_count = target_count or CRAWLER_CONFIG["max_comments_per_post"]
        logger.info(f"获取微博 {mid} 的评论 (期望 {target_count} 条)...")

        # 访问详情页
        url = f"https://weibo.com/{uid}/{mid}"
        if mid not in self.page.url:
            self.page.goto(url)
            self._random_delay(2, 3)

        comments = []

        try:
            logger.debug("等待页面加载...")
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            logger.debug("页面 DOM 已加载")

            # 滚动到评论区
            logger.debug("滚动到评论区...")
            self.page.evaluate("window.scrollBy(0, 500)")
            self._random_delay(2, 3)

            # 尝试切换到热门评论（跳过，默认就是热门排序）
            # logger.debug("尝试点击热门标签...")
            # try:
            #     hot_tab = self.page.locator('text="热门"').first
            #     if hot_tab.is_visible(timeout=2000):
            #         hot_tab.click(timeout=3000)
            #         self._random_delay(1, 2)
            #         logger.debug("已点击热门标签")
            # except Exception as e:
            #     logger.debug(f"点击热门标签失败: {e}")

            # 解析评论（不限制数量，页面返回多少就解析多少）
            # 微博新版评论结构（Vue virtual scroller）:
            # .wbpro-scroller-item > .wbpro-list > .item1 (主评论)
            # .wbpro-scroller-item > .wbpro-list > .list2 > .item2 (子评论)

            try:
                logger.debug("开始查找评论元素...")

                # 直接获取所有主评论的 .con1 元素
                main_comments_elems = self.page.locator('.wbpro-list .item1 .con1').all()
                logger.info(f"找到 {len(main_comments_elems)} 条主评论")

                for elem in main_comments_elems:
                    main_comment = self._parse_comment_from_con(elem, mid, uid)
                    if main_comment:
                        comments.append(main_comment)

                # 获取所有子评论的 .con2 元素
                sub_comments_elems = self.page.locator('.wbpro-list .list2 .item2 .con2').all()
                logger.info(f"找到 {len(sub_comments_elems)} 条子评论")

                for elem in sub_comments_elems:
                    sub_comment = self._parse_comment_from_con(elem, mid, uid, is_sub=True)
                    if sub_comment:
                        comments.append(sub_comment)

            except Exception as e:
                logger.warning(f"评论解析失败: {e}")

                # 回退到旧版选择器
                old_selectors = ['[class*="comment_item"]', '[class*="WB_comment"]']
                for selector in old_selectors:
                    try:
                        comment_elems = self.page.locator(selector).all()
                        if comment_elems:
                            for elem in comment_elems:
                                comment = self._parse_comment(elem, mid, uid)
                                if comment:
                                    comments.append(comment)
                            if comments:
                                break
                    except:
                        continue

            # 注意：这里没有实现翻页逻辑
            # 如果需要更多评论且当前数量不足 target_count，可以在这里添加翻页
            # 但为了减少请求，目前只获取第一页的评论

        except Exception as e:
            logger.warning(f"获取评论失败: {e}")

        logger.info(f"获取到 {len(comments)} 条评论")
        return comments

    def _parse_comment(self, elem, mid: str, blogger_uid: str) -> Optional[dict]:
        """解析单条评论"""
        try:
            comment = {
                "mid": mid,
                "comment_id": None,
                "uid": None,
                "nickname": None,
                "content": None,
                "created_at": None,
                "likes_count": 0,
                "is_blogger_reply": False,
                "reply_to_comment_id": None,
            }

            # 获取评论ID
            try:
                comment_id = elem.get_attribute("id") or elem.get_attribute("data-id")
                if comment_id:
                    comment["comment_id"] = comment_id
            except:
                pass

            # 获取评论者信息 - 适配新版结构 <a href="/u/xxx">昵称</a>
            try:
                user_link = elem.locator("a[href*='/u/']").first
                if user_link.count() > 0:
                    href = user_link.get_attribute("href")
                    match = re.search(r'/u/(\d+)', href)
                    if match:
                        comment["uid"] = match.group(1)
                    comment["nickname"] = user_link.text_content().strip()

                    if comment["uid"] == blogger_uid:
                        comment["is_blogger_reply"] = True
            except:
                pass

            # 获取评论内容 - 适配新版结构
            # 新版结构: <div class="text"><a>用户名</a>:<span>评论内容</span></div>
            try:
                # 先尝试从 span 获取纯评论内容
                span_elem = elem.locator("span").first
                if span_elem.count() > 0:
                    raw_content = span_elem.text_content().strip()
                else:
                    # 回退到获取整个文本
                    raw_content = elem.text_content().strip()
                    # 移除用户名部分（用户名:评论内容）
                    if comment["nickname"] and raw_content.startswith(comment["nickname"]):
                        raw_content = raw_content[len(comment["nickname"]):].lstrip(':：').strip()

                # 检查是否是回复其他人的评论
                # 格式通常是 "回复 @某某某: 评论内容" 或 "回复@某某某：评论内容"
                reply_match = re.match(r'^回复\s*@([^:：\s]+)[：:]\s*(.*)$', raw_content)
                if reply_match:
                    reply_to_nickname = reply_match.group(1)
                    comment["content"] = reply_match.group(2)
                    comment["reply_to_comment_id"] = f"@{reply_to_nickname}"
                else:
                    comment["content"] = raw_content
            except:
                pass

            # 获取点赞数
            try:
                # 尝试从父元素或相邻元素获取点赞数
                parent = elem.locator("..").first
                if parent.count() > 0:
                    like_text = parent.text_content()
                else:
                    like_text = elem.text_content()
                like_match = re.search(r'(\d+)\s*赞', like_text)
                if like_match:
                    comment["likes_count"] = int(like_match.group(1))
            except:
                pass

            # 生成唯一ID
            if not comment["comment_id"] and comment["content"]:
                comment["comment_id"] = f"{mid}_{hash(comment['content'])}"

            if comment["content"]:
                return comment
            return None

        except Exception as e:
            logger.debug(f"解析评论失败: {e}")
            return None

    def _parse_comment_from_con(self, elem, mid: str, blogger_uid: str, is_sub: bool = False) -> Optional[dict]:
        """
        从 .con1 或 .con2 元素解析评论

        结构:
        .con1/.con2
          └── .text
          │     ├── a[usercard="uid"] (用户名)
          │     └── span (评论内容)
          └── .info (时间)
        """
        try:
            comment = {
                "mid": mid,
                "comment_id": None,
                "uid": None,
                "nickname": None,
                "content": None,
                "created_at": None,
                "likes_count": 0,
                "is_blogger_reply": False,
                "reply_to_comment_id": None,
                "reply_to_content": None,
            }

            # 获取用户信息 - 从 usercard 属性获取 uid
            try:
                user_link = elem.locator('.text > a[usercard]').first
                if user_link.count() > 0:
                    comment["uid"] = user_link.get_attribute("usercard")
                    comment["nickname"] = user_link.text_content().strip()
                    if comment["uid"] == blogger_uid:
                        comment["is_blogger_reply"] = True
            except Exception as e:
                logger.debug(f"获取用户信息失败: {e}")

            # 获取评论内容 - 从 span 获取
            try:
                content_span = elem.locator('.text > span').first
                if content_span.count() > 0:
                    comment["content"] = content_span.text_content().strip()
            except Exception as e:
                logger.debug(f"获取评论内容失败: {e}")

            # 获取时间
            try:
                info_elem = elem.locator('.info').first
                if info_elem.count() > 0:
                    info_text = info_elem.text_content().strip()
                    # 格式: "26-1-23 12:13 来自北京"
                    parts = info_text.split()
                    if parts:
                        comment["created_at"] = parts[0]  # "26-1-23"
                        if len(parts) > 1 and ':' in parts[1]:
                            comment["created_at"] += " " + parts[1]  # "26-1-23 12:13"
            except Exception as e:
                logger.debug(f"获取时间失败: {e}")

            # 获取点赞数 - 需要从父元素查找
            try:
                # 向上找到 item1 或 item2，再找 .woo-like-count
                parent_item = elem.locator('xpath=ancestor::div[contains(@class,"item1") or contains(@class,"item2")]').first
                if parent_item.count() > 0:
                    like_elem = parent_item.locator('.woo-like-count').first
                    if like_elem.count() > 0:
                        like_text = like_elem.text_content().strip()
                        if like_text and like_text.isdigit():
                            comment["likes_count"] = int(like_text)
            except Exception as e:
                logger.debug(f"获取点赞数失败: {e}")

            # 生成唯一 ID
            if comment["content"]:
                comment["comment_id"] = f"{mid}_{hash(comment['content'] + (comment['uid'] or ''))}"
                return comment

            return None

        except Exception as e:
            logger.debug(f"解析评论失败: {e}")
            return None

    def _parse_comment_new(self, elem, mid: str, blogger_uid: str, parent_comment: dict = None) -> Optional[dict]:
        """解析单条评论（新版微博 DOM 结构）"""
        try:
            comment = {
                "mid": mid,
                "comment_id": None,
                "uid": None,
                "nickname": None,
                "content": None,
                "created_at": None,
                "likes_count": 0,
                "is_blogger_reply": False,
                "reply_to_comment_id": parent_comment.get("comment_id") if parent_comment else None,
                "reply_to_content": parent_comment.get("content") if parent_comment else None,
            }

            # 获取评论者信息 - <a href="/u/xxx">昵称</a>
            try:
                user_link = elem.locator("a[href*='/u/']").first
                if user_link.count() > 0:
                    href = user_link.get_attribute("href")
                    match = re.search(r'/u/(\d+)', href)
                    if match:
                        comment["uid"] = match.group(1)
                    comment["nickname"] = user_link.text_content().strip()

                    if comment["uid"] == blogger_uid:
                        comment["is_blogger_reply"] = True
            except:
                pass

            # 获取评论内容 - .text 内的 span
            # 结构: <div class="text"><a>昵称</a>:<span>内容</span></div>
            try:
                text_elem = elem.locator('.text').first
                if text_elem.count() > 0:
                    # 尝试从 span 获取纯评论内容
                    span_elem = text_elem.locator('span').first
                    if span_elem.count() > 0:
                        raw_content = span_elem.text_content().strip()
                    else:
                        # 回退到获取整个文本，然后移除用户名部分
                        raw_content = text_elem.text_content().strip()
                        if comment["nickname"] and raw_content.startswith(comment["nickname"]):
                            raw_content = raw_content[len(comment["nickname"]):].lstrip(':：').strip()

                    # 检查是否是回复其他人的评论
                    # 格式: "回复 @某某某: 评论内容" 或 "回复@某某某：评论内容"
                    reply_match = re.match(r'^回复\s*@([^:：\s]+)[：:]\s*(.*)$', raw_content)
                    if reply_match:
                        reply_to_nickname = reply_match.group(1)
                        comment["content"] = reply_match.group(2)
                        # 如果不是回复主评论作者，记录被回复者
                        if parent_comment and reply_to_nickname != parent_comment.get("nickname"):
                            comment["reply_to_comment_id"] = f"@{reply_to_nickname}"
                            comment["reply_to_content"] = None
                    else:
                        comment["content"] = raw_content
            except:
                pass

            # 获取点赞数 - .woo-like-count
            try:
                like_elem = elem.locator('.woo-like-count').first
                if like_elem.count() > 0:
                    like_text = like_elem.text_content().strip()
                    if like_text.isdigit():
                        comment["likes_count"] = int(like_text)
                    elif like_text:
                        # 可能是 "1.2万" 这种格式
                        match = re.search(r'([\d.]+)\s*万?', like_text)
                        if match:
                            num = float(match.group(1))
                            if '万' in like_text:
                                num *= 10000
                            comment["likes_count"] = int(num)
            except:
                pass

            # 获取时间 - .info
            try:
                info_elem = elem.locator('.info').first
                if info_elem.count() > 0:
                    info_text = info_elem.text_content().strip()
                    # 时间通常在最前面，格式如 "1小时前" "昨天 12:30" 等
                    comment["created_at"] = info_text.split('·')[0].strip()
            except:
                pass

            # 生成唯一ID
            if not comment["comment_id"] and comment["content"]:
                comment["comment_id"] = f"{mid}_{hash(comment['content'])}"

            if comment["content"]:
                return comment
            return None

        except Exception as e:
            logger.debug(f"解析评论失败（新版）: {e}")
            return None

    def _parse_sub_comments(self, parent_elem, mid: str, blogger_uid: str, parent_comment: dict) -> list:
        """
        解析楼中楼（子评论），不额外请求
        在已加载的页面中解析主评论下的子评论

        参数:
            parent_elem: 主评论的 DOM 元素
            mid: 微博ID
            blogger_uid: 博主ID
            parent_comment: 主评论数据（用于关联和记录被回复内容）

        返回:
            子评论列表
        """
        sub_comments = []

        try:
            # 尝试多种子评论选择器
            sub_selectors = [
                '[class*="reply_item"]',
                '[class*="reply_list"] [class*="item"]',
                '[class*="sub_comment"]',
                '[class*="child_comment"]',
            ]

            for selector in sub_selectors:
                try:
                    sub_elems = parent_elem.locator(selector).all()
                    if sub_elems:
                        for sub_elem in sub_elems:
                            sub_comment = self._parse_single_sub_comment(
                                sub_elem, mid, blogger_uid, parent_comment
                            )
                            if sub_comment:
                                sub_comments.append(sub_comment)
                        break
                except:
                    continue

        except Exception as e:
            logger.debug(f"解析子评论失败: {e}")

        return sub_comments

    def _parse_single_sub_comment(self, elem, mid: str, blogger_uid: str, parent_comment: dict) -> Optional[dict]:
        """解析单条子评论"""
        try:
            comment = {
                "mid": mid,
                "comment_id": None,
                "uid": None,
                "nickname": None,
                "content": None,
                "created_at": None,
                "likes_count": 0,
                "is_blogger_reply": False,
                "reply_to_comment_id": parent_comment.get("comment_id"),  # 关联到主评论
                "reply_to_content": parent_comment.get("content"),  # 记录被回复的内容
            }

            # 获取评论者信息
            try:
                user_link = elem.locator("a[href*='/u/']").first
                if user_link.count() > 0:
                    href = user_link.get_attribute("href")
                    match = re.search(r'/u/(\d+)', href)
                    if match:
                        comment["uid"] = match.group(1)
                    comment["nickname"] = user_link.text_content().strip()

                    if comment["uid"] == blogger_uid:
                        comment["is_blogger_reply"] = True
            except:
                pass

            # 获取评论内容
            try:
                content_elem = elem.locator('[class*="text"]').first
                if content_elem.count() > 0:
                    raw_content = content_elem.text_content().strip()

                    # 检查是否回复其他人（可能回复的不是主评论，而是其他子评论）
                    reply_match = re.match(r'^回复\s*@([^:：\s]+)[：:]\s*(.*)$', raw_content)
                    if reply_match:
                        reply_to_nickname = reply_match.group(1)
                        comment["content"] = reply_match.group(2)
                        # 如果回复的不是主评论作者，更新 reply_to
                        if reply_to_nickname != parent_comment.get("nickname"):
                            comment["reply_to_comment_id"] = f"@{reply_to_nickname}"
                            comment["reply_to_content"] = None  # 无法获取被回复的具体内容
                    else:
                        comment["content"] = raw_content
            except:
                pass

            # 获取点赞数
            try:
                like_text = elem.text_content()
                like_match = re.search(r'(\d+)\s*赞', like_text)
                if like_match:
                    comment["likes_count"] = int(like_match.group(1))
            except:
                pass

            # 生成唯一ID
            if not comment["comment_id"] and comment["content"]:
                comment["comment_id"] = f"{mid}_sub_{hash(comment['content'])}"

            if comment["content"]:
                return comment
            return None

        except Exception as e:
            logger.debug(f"解析子评论失败: {e}")
            return None

    def crawl_blogger(self, uid: str, mode: str = "new"):
        """
        抓取单个博主的微博和评论

        参数:
            uid: 博主ID
            mode: 抓取模式
                - "new": 只抓取新微博（从最新开始，遇到已入库的就停止）
                - "history": 继续向后抓取历史微博（从上次停下的位置继续）
                - "all": 先抓新的，再抓历史
        """
        logger.info(f"开始抓取博主: {uid}, 模式: {mode}")

        # 获取博主信息
        blogger_info = self.get_blogger_info(uid)
        if not blogger_info:
            logger.error(f"无法获取博主信息: {uid}")
            return

        # 获取已有的抓取边界
        newest_mid = get_blogger_newest_mid(uid)
        oldest_mid = get_blogger_oldest_mid(uid)

        logger.info(f"已有记录 - 最新: {newest_mid}, 最老: {oldest_mid}")

        posts_to_process = []

        history_complete = False  # 标记历史是否已抓完（到达时间截止点）

        if mode in ("new", "all"):
            # 抓取新微博：从最新开始，遇到已入库的停止
            logger.info("=== 检查新微博 ===")
            posts, _, _ = self.get_post_list_via_api(uid, since_id=None)

            for post in posts:
                if is_post_exists(post["mid"]):
                    logger.info(f"遇到已入库微博 {post['mid']}，停止向前抓取")
                    break
                posts_to_process.append(post)

            if posts_to_process:
                logger.info(f"发现 {len(posts_to_process)} 条新微博")
            else:
                logger.info("没有新微博")

        if mode in ("history", "all"):
            # 抓取历史：从最老的微博之后继续
            if oldest_mid:
                logger.info(f"=== 继续抓取历史微博 (从 {oldest_mid} 之后) ===")
                # 使用 oldest_mid 作为 since_id 继续向后翻页，检查时间范围
                history_posts, _, reached_cutoff = self.get_post_list_via_api(
                    uid, since_id=oldest_mid, check_date=True
                )

                for post in history_posts:
                    if not is_post_exists(post["mid"]):
                        posts_to_process.append(post)

                logger.info(f"获取到 {len(history_posts)} 条历史微博")

                if reached_cutoff:
                    history_complete = True
                    logger.info(f"✅ 博主 {uid} 的 {CRAWLER_CONFIG.get('max_days', 180)} 天内历史微博已全部抓取完成")
            else:
                logger.info("首次抓取，无历史记录")

        if not posts_to_process:
            logger.info(f"博主 {uid} 没有需要处理的微博")
            return

        # 处理每条微博
        for i, post in enumerate(posts_to_process):
            mid = post["mid"]
            logger.info(f"处理第 {i+1}/{len(posts_to_process)} 条微博: {mid}")

            # 如果是长文本，获取全文
            if post.get("is_long_text"):
                full_text = self.get_post_full_text(uid, mid)
                if full_text:
                    post["content"] = full_text

            # 保存微博
            is_new_post = save_post(post)

            if is_new_post:
                logger.info(f"微博已保存: {mid}")
                # 更新抓取进度
                update_crawl_progress(uid, mid, post.get("created_at", ""), is_newer=(mode == "new"))

                # 下载图片并更新数据库
                if post.get("images"):
                    local_paths = self.download_images(post)
                    if local_paths:
                        update_post_local_images(mid, local_paths)

            # 获取评论（微博发布 N 天后才抓取，让评论稳定下来）
            api_comment_count = post.get("comments_count", 0)
            existing_comment_count = get_post_comment_count(mid)
            comment_delay_days = CRAWLER_CONFIG.get("comment_delay_days", 3)

            # 检查微博是否已发布足够久
            post_age_ok = False
            if post.get("created_at"):
                try:
                    from datetime import timedelta
                    post_date = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                    post_age = datetime.now() - post_date.replace(tzinfo=None)
                    post_age_ok = post_age.days >= comment_delay_days
                    if not post_age_ok:
                        logger.info(f"微博发布不足 {comment_delay_days} 天，跳过评论抓取")
                except:
                    post_age_ok = True  # 解析失败时默认抓取

            if api_comment_count > 0 and existing_comment_count == 0 and post_age_ok:
                # 有评论、还没抓过、且已发布足够久
                comments = self.get_comments(uid, mid)
                saved_count = 0
                for comment in comments:
                    if save_comment(comment):
                        saved_count += 1
                logger.info(f"保存了 {saved_count} 条评论")
            elif existing_comment_count > 0:
                logger.info(f"评论已抓取过 ({existing_comment_count} 条)，跳过")
            elif api_comment_count == 0:
                logger.info("该微博无评论")

            if not is_new_post:
                logger.debug(f"微博已存在: {mid}")

            self._random_delay()

        logger.info(f"博主 {uid} 抓取完成")


def run_crawler(blogger_uids: list, mode: str = "new"):
    """
    运行爬虫主函数

    参数:
        blogger_uids: 博主ID列表
        mode: 抓取模式 (new/history/all)
    """
    global _crawler_instance

    init_database()

    crawler = WeiboCrawler()
    _crawler_instance = crawler  # 注册到全局，方便信号处理
    try:
        crawler.start()

        if not crawler.check_login_status():
            logger.info("需要登录...")
            if not crawler.login():
                logger.error("登录失败，退出")
                return

        for uid in blogger_uids:
            try:
                crawler.crawl_blogger(uid, mode=mode)
            except Exception as e:
                logger.error(f"抓取博主 {uid} 时出错: {e}")
                import traceback
                traceback.print_exc()
                continue

    finally:
        crawler.stop()
