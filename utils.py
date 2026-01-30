"""
工具函数模块

职责：
- 通用时间解析
- 随机延迟
- 其他共享工具函数
"""
import random
import re
import time
from datetime import datetime, timedelta

from logger import get_logger

logger = get_logger(__name__)


def parse_weibo_time(time_str: str) -> str:
    """解析微博时间字符串，统一输出为 YYYY-MM-DD HH:MM 格式

    支持格式:
    - 刚刚
    - N分钟前
    - N小时前
    - 昨天 HH:MM
    - MM-DD
    - YY-MM-DD HH:MM
    - YYYY-MM-DD HH:MM
    - Wed Jan 01 12:00:00 +0800 2025
    """
    if not time_str:
        return ""

    time_str = time_str.strip()
    now = datetime.now()

    # 刚刚
    if "刚刚" in time_str:
        return now.strftime("%Y-%m-%d %H:%M")

    # N分钟前
    match = re.search(r'(\d+)\s*分钟前', time_str)
    if match:
        dt = now - timedelta(minutes=int(match.group(1)))
        return dt.strftime("%Y-%m-%d %H:%M")

    # N小时前
    match = re.search(r'(\d+)\s*小时前', time_str)
    if match:
        dt = now - timedelta(hours=int(match.group(1)))
        return dt.strftime("%Y-%m-%d %H:%M")

    # 昨天 HH:MM
    match = re.search(r'昨天\s*(\d{1,2}):(\d{2})', time_str)
    if match:
        yesterday = now - timedelta(days=1)
        dt = yesterday.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0)
        return dt.strftime("%Y-%m-%d %H:%M")

    # MM-DD (当年)
    match = re.match(r'^(\d{1,2})-(\d{1,2})$', time_str)
    if match:
        dt = now.replace(month=int(match.group(1)), day=int(match.group(2)), hour=0, minute=0, second=0)
        return dt.strftime("%Y-%m-%d %H:%M")

    # YY-MM-DD HH:MM (两位数年份)
    match = re.match(r'^(\d{2})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$', time_str)
    if match:
        year, month, day, hour, minute = match.groups()
        full_year = 2000 + int(year)
        return f"{full_year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}"

    # YYYY-MM-DD HH:MM (已是目标格式)
    match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$', time_str)
    if match:
        year, month, day, hour, minute = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}"

    # RFC 2822 格式: Wed Jan 01 12:00:00 +0800 2025
    try:
        dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
        return dt.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass

    return time_str


def random_delay(base_delay: float, log_level: str = "debug"):
    """随机延迟（基准值的 ±25%）

    Args:
        base_delay: 基准延迟秒数
        log_level: 日志级别 ("debug" 或 "info")
    """
    delay = random.uniform(base_delay * 0.75, base_delay * 1.25)
    if log_level == "info":
        logger.info(f"等待 {delay:.1f} 秒...")
        print()
    else:
        logger.debug(f"等待 {delay:.1f} 秒...")
    time.sleep(delay)
