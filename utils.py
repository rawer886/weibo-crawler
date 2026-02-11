"""
工具函数模块

职责：
- 通用时间解析
- 随机延迟
- mid 格式转换
- 其他共享工具函数
"""
import random
import re
import time
from datetime import datetime, timedelta

from logger import get_logger

logger = get_logger(__name__)

# Base62 字符表（微博 mid 编码用）
BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def mid_to_numeric(mid: str) -> str:
    """将短格式 mid（base62）转换为纯数字 mid

    微博 mid 编码规则：
    - 纯数字 mid 按每 7 位分组，每组独立转为 base62（4位）
    - 最后不足 7 位的部分单独转换

    示例: QrkVr3ze5 -> 5132657891234567
    """
    if not mid:
        return mid

    # 已经是纯数字，直接返回
    if mid.isdigit():
        return mid

    # base62 解码
    def base62_decode(s: str) -> int:
        result = 0
        for char in s:
            result = result * 62 + BASE62_CHARS.index(char)
        return result

    # 按 4 位分组解码（对应数字 mid 的 7 位）
    # 短 mid 分组方式：从右往左，每 4 位一组，最左边可能不足 4 位
    result = ""
    mid_len = len(mid)

    # 计算分组
    groups = []
    i = mid_len
    while i > 0:
        start = max(0, i - 4)
        groups.insert(0, mid[start:i])
        i = start

    # 解码每组
    for idx, group in enumerate(groups):
        num = base62_decode(group)
        if idx == 0:
            # 第一组不补零
            result += str(num)
        else:
            # 后续组补零到 7 位
            result += str(num).zfill(7)

    return result


def numeric_to_mid(numeric_mid: str) -> str:
    """将纯数字 mid 转换为短格式 mid（base62）

    示例: 5132657891234567 -> QrkVr3ze5
    """
    if not numeric_mid:
        return numeric_mid

    # 已经是短格式，直接返回
    if not numeric_mid.isdigit():
        return numeric_mid

    # base62 编码
    def base62_encode(num: int) -> str:
        if num == 0:
            return "0"
        result = ""
        while num > 0:
            result = BASE62_CHARS[num % 62] + result
            num //= 62
        return result

    # 按 7 位分组编码
    result = ""
    numeric_len = len(numeric_mid)

    # 从右往左，每 7 位一组
    groups = []
    i = numeric_len
    while i > 0:
        start = max(0, i - 7)
        groups.insert(0, numeric_mid[start:i])
        i = start

    # 编码每组
    for idx, group in enumerate(groups):
        encoded = base62_encode(int(group))
        if idx == 0:
            # 第一组不补零
            result += encoded
        else:
            # 后续组补零到 4 位
            result += encoded.zfill(4)

    return result


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
