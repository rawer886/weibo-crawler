"""
浏览器控制模块

职责：
- Playwright 浏览器启动/停止
- Cookie 管理（加载/保存）
- 登录状态检查
"""
import json
import os
import random
import time
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser

from config import CRAWLER_CONFIG
from logger import get_logger

logger = get_logger(__name__)


class BrowserManager:
    """浏览器管理器"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.is_logged_in = False
        self.cookies_for_request = {}  # 用于 requests 库的 cookies

    def start(self, url: str = None):
        """启动浏览器

        参数:
            url: 可选，启动后直接访问的URL
        """
        logger.info("启动浏览器...")
        self.playwright = sync_playwright().start()

        # 获取屏幕尺寸
        viewport_height = 900
        viewport_width = 720
        try:
            from screeninfo import get_monitors
            monitors = get_monitors()
            if monitors:
                primary = monitors[0]
                viewport_height = primary.height - 130
                viewport_width = primary.width // 2
                logger.info(f"检测到显示器: {primary.width}x{primary.height}, 设置视口: {viewport_width}x{viewport_height}")
        except ImportError:
            logger.debug("screeninfo 未安装，使用默认视口大小")
        except Exception as e:
            logger.debug(f"获取显示器尺寸失败: {e}")

        # 启动浏览器
        self.browser = self.playwright.chromium.launch(
            headless=CRAWLER_CONFIG["headless"],
            args=[
                f"--window-size={viewport_width},{viewport_height + 28}",
                "--window-position=0,25",
            ]
        )

        self.page = self.browser.new_page(viewport={"width": viewport_width, "height": viewport_height})
        self.page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        # 加载已保存的 cookies
        self._load_cookies()

        if url:
            logger.info(f"访问页面: {url}")
            self.page.goto(url)

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
        logger.info("Cookies 已更新\n")

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

    def login(self) -> bool:
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
        self._random_delay(2.5)

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

        try:
            current_url = self.page.url
            if not current_url or "weibo.com" not in current_url:
                self.page.goto("https://weibo.com")
                self._random_delay(2.5)

            self.page.wait_for_load_state("networkidle", timeout=15000)

            # 检查是否被重定向到登录页
            if "login" in self.page.url.lower() or "passport" in self.page.url.lower():
                self.is_logged_in = False
                return False

            # 检查页面是否有登录用户的特征
            try:
                user_avatar = self.page.locator('[class*="avatar"]').first
                if user_avatar.count() > 0:
                    self.is_logged_in = True
                    self._save_cookies()
                    return True
            except:
                pass

            # 备用检查：查看是否有登录按钮
            try:
                login_btn = self.page.locator('text="登录"').first
                if login_btn.count() > 0 and login_btn.is_visible(timeout=1000):
                    self.is_logged_in = False
                    return False
            except:
                pass

            self.is_logged_in = True
            self._save_cookies()
            return True

        except Exception as e:
            logger.warning(f"检查登录状态失败: {e}")
            return False

    def _random_delay(self, base_delay: float = None):
        """随机延迟"""
        base = base_delay or CRAWLER_CONFIG["delay"]
        delay = random.uniform(base * 0.5, base * 1.5)
        logger.debug(f"等待 {delay:.1f} 秒...")
        time.sleep(delay)

    def goto(self, url: str):
        """导航到指定 URL"""
        self.page.goto(url)

    def smooth_scroll_to_element(self, element):
        """平滑滚动到元素位置"""
        try:
            element.evaluate("""
                el => el.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                })
            """)
            self._random_delay(0.75)
        except Exception as e:
            logger.debug(f"平滑滚动失败: {e}")
            element.scroll_into_view_if_needed()

    def scroll_page(self, distance: int):
        """滚动页面"""
        self.page.evaluate(f"""
            () => {{
                window.scrollBy({{
                    top: {distance},
                    behavior: 'smooth'
                }});
            }}
        """)
