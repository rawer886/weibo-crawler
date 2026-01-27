"""
微博 API 模块

职责：
- 移动端 API 调用
- API 响应缓存
- 博主信息获取
- 微博列表获取
"""
import hashlib
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

import requests

from config import CRAWLER_CONFIG

logger = logging.getLogger(__name__)


class APICache:
    """API 响应持久化缓存"""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _get_cache_path(self, key: str) -> str:
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}.json")

    def get(self, key: str, max_age: float = None) -> Optional[dict]:
        """获取缓存，不存在或已过期返回 None

        参数:
            key: 缓存键
            max_age: 最大缓存时间（秒），None 表示永不过期
        """
        cache_path = self._get_cache_path(key)
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)

            # 检查缓存是否过期
            if max_age is not None:
                cached_at = cached.get("_cached_at", 0)
                if time.time() - cached_at > max_age:
                    return None

            return cached.get("data")
        except Exception:
            return None

    def set(self, key: str, data: dict):
        """设置缓存"""
        cache_path = self._get_cache_path(key)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"_cached_at": time.time(), "data": data}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")

    def clear(self):
        """清除所有缓存"""
        try:
            for f in os.listdir(self.cache_dir):
                if f.endswith(".json"):
                    os.remove(os.path.join(self.cache_dir, f))
        except Exception as e:
            logger.warning(f"清除缓存失败: {e}")


class WeiboAPI:
    """微博 API 客户端"""

    MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"

    def __init__(self, cookies: dict = None):
        self.cookies = cookies or {}
        self.cache = APICache(CRAWLER_CONFIG.get("cache_dir", "cache"))

    def set_cookies(self, cookies: dict):
        """更新 cookies"""
        self.cookies = cookies

    def get_blogger_info(self, uid: str) -> Optional[dict]:
        """获取博主信息"""
        cache_key = f"blogger_{uid}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info(f"使用缓存的博主信息: {uid}")
            return cached

        url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}"
        headers = {"User-Agent": self.MOBILE_UA, "Referer": f"https://m.weibo.cn/u/{uid}"}

        try:
            resp = requests.get(url, headers=headers, cookies=self.cookies, timeout=10)
            data = resp.json()

            if data.get("ok") == 1:
                user_info = data.get("data", {}).get("userInfo", {})
                blogger_info = {
                    "uid": uid,
                    "nickname": user_info.get("screen_name", f"用户{uid}"),
                    "description": user_info.get("description", ""),
                    "followers_count": user_info.get("followers_count", 0),
                }
                self.cache.set(cache_key, blogger_info)
                logger.info(f"博主信息: {blogger_info['nickname']} (粉丝: {blogger_info['followers_count']})")
                return blogger_info
        except Exception as e:
            logger.error(f"获取博主信息失败: {e}")

        return None

    def _fetch_with_cache(self, url: str, cache_key: str, max_age: float = None) -> Optional[dict]:
        """带缓存的 API 请求

        参数:
            url: 请求 URL
            cache_key: 缓存键
            max_age: 缓存策略:
                - None: 使用永久缓存
                - 0: 跳过缓存读取（仍会写入）
                - >0: 缓存有效期（秒）
        """
        skip_cache_read = max_age == 0
        if not skip_cache_read:
            effective_max_age = max_age if max_age and max_age > 0 else None
            cached = self.cache.get(cache_key, max_age=effective_max_age)
            if cached is not None:
                logger.info(f"命中缓存: {cache_key}")
                return cached

        headers = {"User-Agent": self.MOBILE_UA, "Referer": "https://m.weibo.cn/"}

        try:
            resp = requests.get(url, headers=headers, cookies=self.cookies, timeout=10)
            data = resp.json()

            if data.get("ok") == 1:
                self.cache.set(cache_key, data)

            return data
        except Exception as e:
            logger.error(f"API 请求失败: {e}")
            return None

    def get_post_list(self, uid: str, since_id: str = None, max_count: int = None,
                      check_date: bool = False, cache_max_age: float = None) -> Tuple[List[dict], str, bool]:
        """获取微博列表

        参数:
            uid: 博主 ID
            since_id: 从此 ID 开始向更早的方向获取
            max_count: 最大获取数量
            check_date: 是否检查时间范围
            cache_max_age: 缓存策略:
                - None: 使用永久缓存（默认）
                - 0: 跳过缓存读取（仍会写入）
                - >0: 缓存有效期（秒）

        返回: (微博列表, 下一页since_id, 是否到达时间截止点)
        """
        max_count = max_count or CRAWLER_CONFIG.get("max_posts_per_run", 50)
        max_days = CRAWLER_CONFIG.get("max_days", 180)
        cutoff_date = datetime.now() - timedelta(days=max_days)
        container_id = f"107603{uid}"

        posts = []
        current_since_id = since_id
        page = 1
        reached_cutoff = False

        while len(posts) < max_count:
            url = f"https://m.weibo.cn/api/container/getIndex?containerid={container_id}"
            if current_since_id:
                url += f"&since_id={current_since_id}"

            cache_key = f"posts_{uid}_{current_since_id or 'first'}"

            cache_hint = self._format_cache_hint(cache_max_age)
            logger.info(f"获取第 {page} 页微博列表{cache_hint}")
            data = self._fetch_with_cache(url, cache_key, max_age=cache_max_age)

            try:
                if not data or data.get("ok") != 1:
                    break

                cards = data.get("data", {}).get("cards", [])
                if not cards:
                    logger.info("没有更多微博了")
                    break

                for card in cards:
                    if card.get("card_type") != 9:
                        continue

                    mblog = card.get("mblog", {})
                    mid = mblog.get("id") or mblog.get("mid")
                    if not mid:
                        continue

                    post = self._parse_post_from_api(mblog, uid)

                    # 检查时间范围
                    if check_date and post["created_at"]:
                        try:
                            post_date = datetime.strptime(post["created_at"], "%Y-%m-%d %H:%M")
                            if post_date < cutoff_date:
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

                # 获取下一页 since_id
                card_info = data.get("data", {}).get("cardlistInfo", {})
                current_since_id = card_info.get("since_id")

                if not current_since_id:
                    logger.info("已到达最后一页")
                    break

                page += 1
                time.sleep(1.5)

            except Exception as e:
                logger.error(f"获取微博列表失败: {e}")
                break

        logger.info(f"共获取 {len(posts)} 条微博")
        return posts, current_since_id, reached_cutoff

    def _parse_post_from_api(self, mblog: dict, uid: str) -> dict:
        """从 API 响应解析微博数据"""
        mid = str(mblog.get("id") or mblog.get("mid"))

        post = {
            "mid": mid,
            "uid": uid,
            "content": self._clean_html(mblog.get("text", "")),
            "created_at": self._parse_weibo_time(mblog.get("created_at", "")),
            "reposts_count": mblog.get("reposts_count", 0),
            "comments_count": mblog.get("comments_count", 0),
            "likes_count": mblog.get("attitudes_count", 0),
            "is_repost": mblog.get("retweeted_status") is not None,
            "repost_content": None,
            "repost_images": [],
            "images": [],
            "source_url": f"https://weibo.com/{uid}/{mid}",
            "is_long_text": mblog.get("isLongText", False),
        }

        # 转发内容
        if post["is_repost"] and mblog.get("retweeted_status"):
            rt = mblog["retweeted_status"]
            post["repost_content"] = self._clean_html(rt.get("text", ""))

            # 原微博图片
            for pic in rt.get("pics", []):
                large_url = pic.get("large", {}).get("url") or pic.get("url")
                if large_url:
                    post["repost_images"].append(large_url)

        # 当前微博图片
        for pic in mblog.get("pics", []):
            large_url = pic.get("large", {}).get("url") or pic.get("url")
            if large_url:
                post["images"].append(large_url)

        return post

    def _format_cache_hint(self, cache_max_age: float) -> str:
        """格式化缓存提示信息"""
        if cache_max_age == 0:
            return "（不使用缓存）"
        if cache_max_age is not None and cache_max_age > 0:
            return f"（缓存有效期: {cache_max_age/3600:.0f}h）"
        return ""

    def _clean_html(self, html_text: str) -> str:
        """清理 HTML 标签"""
        if not html_text:
            return ""
        text = re.sub(r'<[^>]+>', '', html_text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _parse_weibo_time(self, time_str: str) -> str:
        """解析微博时间字符串，统一输出为 YYYY-MM-DD HH:MM 格式"""
        if not time_str:
            return ""

        now = datetime.now()
        dt = None

        try:
            if "刚刚" in time_str:
                dt = now

            if not dt:
                match = re.search(r'(\d+)\s*分钟前', time_str)
                if match:
                    dt = now - timedelta(minutes=int(match.group(1)))

            if not dt:
                match = re.search(r'(\d+)\s*小时前', time_str)
                if match:
                    dt = now - timedelta(hours=int(match.group(1)))

            if not dt:
                match = re.search(r'昨天\s*(\d{1,2}):(\d{2})', time_str)
                if match:
                    yesterday = now - timedelta(days=1)
                    dt = yesterday.replace(
                        hour=int(match.group(1)),
                        minute=int(match.group(2)),
                        second=0
                    )

            if not dt:
                match = re.match(r'^(\d{1,2})-(\d{1,2})$', time_str.strip())
                if match:
                    dt = now.replace(
                        month=int(match.group(1)),
                        day=int(match.group(2)),
                        hour=0, minute=0, second=0
                    )

            # YY-MM-DD HH:MM 格式（两位数年份），转换为四位数年份
            if not dt:
                match = re.match(r'^(\d{2})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$', time_str.strip())
                if match:
                    year, month, day, hour, minute = match.groups()
                    full_year = 2000 + int(year)
                    return f"{full_year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}"

            # YYYY-MM-DD HH:MM 格式（四位数年份），已是目标格式
            if not dt:
                match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$', time_str.strip())
                if match:
                    year, month, day, hour, minute = match.groups()
                    return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}"

            if not dt:
                try:
                    dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
                    dt = dt.replace(tzinfo=None)
                except:
                    pass

            if dt:
                return dt.strftime("%Y-%m-%d %H:%M")

            return time_str
        except Exception as e:
            logger.debug(f"解析时间失败: {time_str}, {e}")
            return time_str
