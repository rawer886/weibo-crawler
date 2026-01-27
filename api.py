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

    def get(self, key: str) -> Optional[dict]:
        """获取缓存，不存在返回 None"""
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
        logger.info(f"获取博主信息: {uid}")

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

    def _fetch_with_cache(self, url: str, cache_key: str) -> Optional[dict]:
        """带缓存的 API 请求"""
        is_first_page = cache_key.endswith("_first")

        if not is_first_page:
            cached = self.cache.get(cache_key)
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
                      check_date: bool = False) -> Tuple[List[dict], str, bool]:
        """获取微博列表

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

            is_first_page = current_since_id is None
            cache_key = f"posts_{uid}_{current_since_id or 'first'}"

            try:
                logger.info(f"获取第 {page} 页微博列表..." + (" (不缓存)" if is_first_page else ""))
                data = self._fetch_with_cache(url, cache_key)

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
            "images": [],
            "source_url": f"https://weibo.com/{uid}/{mid}",
            "is_long_text": mblog.get("isLongText", False),
        }

        # 转发内容
        if post["is_repost"] and mblog.get("retweeted_status"):
            rt = mblog["retweeted_status"]
            post["repost_content"] = self._clean_html(rt.get("text", ""))
            rt_user = rt.get("user", {})
            if rt_user:
                post["repost_uid"] = str(rt_user.get("id", ""))
                post["repost_nickname"] = rt_user.get("screen_name", "")

            # 原微博图片
            for pic in rt.get("pics", []):
                large_url = pic.get("large", {}).get("url") or pic.get("url")
                if large_url:
                    post["images"].append(large_url)

        # 当前微博图片
        for pic in mblog.get("pics", []):
            large_url = pic.get("large", {}).get("url") or pic.get("url")
            if large_url:
                post["images"].append(large_url)

        return post

    def _clean_html(self, html_text: str) -> str:
        """清理 HTML 标签"""
        if not html_text:
            return ""
        text = re.sub(r'<[^>]+>', '', html_text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _parse_weibo_time(self, time_str: str) -> str:
        """解析微博时间字符串"""
        if not time_str:
            return ""

        now = datetime.now()

        try:
            if "刚刚" in time_str:
                return now.isoformat()

            match = re.search(r'(\d+)\s*分钟前', time_str)
            if match:
                minutes = int(match.group(1))
                return (now - timedelta(minutes=minutes)).isoformat()

            match = re.search(r'(\d+)\s*小时前', time_str)
            if match:
                hours = int(match.group(1))
                return (now - timedelta(hours=hours)).isoformat()

            match = re.search(r'昨天\s*(\d{1,2}):(\d{2})', time_str)
            if match:
                hour, minute = int(match.group(1)), int(match.group(2))
                yesterday = now - timedelta(days=1)
                return yesterday.replace(hour=hour, minute=minute, second=0).isoformat()

            match = re.match(r'^(\d{1,2})-(\d{1,2})$', time_str.strip())
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                return now.replace(month=month, day=day, hour=0, minute=0, second=0).isoformat()

            try:
                dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
                return dt.isoformat()
            except:
                pass

            return time_str
        except Exception as e:
            logger.debug(f"解析时间失败: {time_str}, {e}")
            return time_str
