# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

微博爬虫 (Weibo Crawler) - A Python web scraper for extracting Weibo posts and comments. Uses Playwright for browser automation, supports resume capability, comment reply relationships, and image downloading.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Crawl single post
python main.py https://weibo.com/1497035431/AbCdEfGhI

# Bulk crawl user posts (stable posts only, >1 day old)
python main.py https://weibo.com/u/1497035431

# Bulk crawl including new posts
python main.py https://weibo.com/u/1497035431 --mode new

# Utility scripts
python scripts/show_stats.py              # Database statistics
python scripts/show_post.py <mid>         # View post and comments
python scripts/show_post.py <mid> -b      # View blogger comments only
python scripts/show_blogger_replies.py <uid>  # View all blogger replies
python scripts/delete_comments.py <mid>   # Delete comments for a post
python scripts/delete_post.py <mid>       # Delete a post

# Direct database access
sqlite3 ../data/weibo.db "SELECT * FROM bloggers"
```

## Architecture

**Entry Flow:** `main.py` → `commands.py` → `WeiboCrawler` (crawler.py)

**Core Modules:**
- `crawler.py` - Orchestrates crawling, coordinates all modules
- `browser.py` - Playwright browser lifecycle, cookie persistence, login handling
- `api.py` - Weibo mobile API client with `APICache` for persistent caching
- `parser.py` - DOM parsing for posts/comments from Playwright pages
- `database.py` - SQLite operations with context-managed connections
- `image.py` - Downloads and organizes images by `{uid}/{YYYY-MM}/{mid}_{index}.jpg`
- `display.py` - Formatted console output
- `logger.py` - Colored console + file logging
- `utils.py` - Time parsing utilities

**Data Directory:** `../data/` (sibling to project) contains:
- `weibo.db` - SQLite database
- `cookies.json` - Browser session
- `cache/` - API response cache
- `images/` - Downloaded images
- `logs/` - Execution logs

**Database Tables:**
- `bloggers` - User info (uid, nickname, followers_count)
- `posts` - Posts with `detail_status` tracking (0=pending, 1=fetched)
- `comments` - Comments with reply relationships and blogger_reply flag
- `crawl_progress` - Tracks `list_scan_oldest_mid` per user

## Key Implementation Details

**URL Formats:** Supports `/u/UID`, `/UID`, `/UID/MID` - MID can be alphanumeric or numeric

**Anti-Risk Strategy:** Configurable delay (default 15s + random jitter) between requests. Edit `config.py` to adjust.

**Login:** First run opens browser for manual login. Cookies saved to `cookies.json`. Delete this file to re-login.

**Graceful Shutdown:** First Ctrl+C stops gracefully, second force exits. Uses global `_stopping` flag.

**On-demand List Fetching:** History mode fetches post lists on-demand when the pending queue runs low.

**Time Normalization:** All dates stored as `YYYY-MM-DD HH:MM`. `utils.parse_weibo_time()` handles various input formats.
