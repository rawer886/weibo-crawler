#!/usr/bin/env python3
"""
clean_images.py - 按 MD5 清理图片

根据 MD5 值删除指定的图片文件，并更新数据库中的图片路径引用。
用于清理占位图、损坏图片等无效文件。

使用方法:
    python scripts/clean_images.py [--dry-run]

    --dry-run  只显示要删除的文件，不实际执行

配置:
    修改 PLACEHOLDER_MD5_LIST 列表，添加要删除的图片 MD5 值
"""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# 项目路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
DATABASE_PATH = os.path.join(DATA_DIR, "weibo.db")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

# 要删除的图片 MD5 列表
PLACEHOLDER_MD5_LIST = [
    # "79c22a46d6fc1aa9e264a2c8037f0ec2",  # 示例：侧边栏占位图
]


def calculate_md5(filepath: str) -> str:
    """计算文件 MD5"""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def backup_database():
    """备份数据库"""
    if not os.path.exists(DATABASE_PATH):
        print(f"[错误] 数据库不存在: {DATABASE_PATH}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{DATABASE_PATH}.backup_{timestamp}"
    shutil.copy2(DATABASE_PATH, backup_path)
    print(f"[备份] 数据库已备份到: {backup_path}")
    return backup_path


def scan_images(dry_run: bool = False) -> list:
    """扫描图片目录，找出要删除的文件"""
    files_to_delete = []

    if not os.path.exists(IMAGES_DIR):
        print(f"[错误] 图片目录不存在: {IMAGES_DIR}")
        return files_to_delete

    total_files = 0
    for root, dirs, files in os.walk(IMAGES_DIR):
        for filename in files:
            if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                continue

            filepath = os.path.join(root, filename)
            total_files += 1

            try:
                md5 = calculate_md5(filepath)
                if md5 in PLACEHOLDER_MD5_LIST:
                    # 相对路径（相对于 IMAGES_DIR）
                    relative_path = os.path.relpath(filepath, IMAGES_DIR)
                    files_to_delete.append({
                        "filepath": filepath,
                        "relative_path": relative_path,
                        "md5": md5,
                    })
                    print(f"[发现] {relative_path} (MD5: {md5})")
            except Exception as e:
                print(f"[警告] 无法读取文件 {filepath}: {e}")

    print(f"\n[统计] 扫描了 {total_files} 个图片文件，发现 {len(files_to_delete)} 个匹配图片")
    return files_to_delete


def _update_media_field(cursor, table: str, field: str, id_field: str,
                         deleted_set: set, dry_run: bool) -> int:
    """更新 posts 表的 media/repost_media 字段，返回更新数量"""
    updated = 0
    cursor.execute(f"SELECT {id_field}, {field} FROM {table} WHERE {field} IS NOT NULL")

    for row_id, media_json in cursor.fetchall():
        if not media_json:
            continue

        try:
            media = json.loads(media_json)
            images = media.get("images", [])
            modified = False

            for img in images:
                local_path = img.get("local")
                if local_path and local_path in deleted_set:
                    img["local"] = None
                    modified = True
                    print(f"[更新] {table}.{field} {id_field}={row_id}: 移除 {local_path}")

            if modified:
                if not dry_run:
                    cursor.execute(
                        f"UPDATE {table} SET {field} = ? WHERE {id_field} = ?",
                        (json.dumps(media, ensure_ascii=False), row_id)
                    )
                updated += 1
        except json.JSONDecodeError:
            pass

    return updated


def update_database(deleted_paths: list, dry_run: bool = False):
    """更新数据库，移除被删除的图片路径"""
    if not deleted_paths:
        print("[信息] 没有需要更新的数据库记录")
        return

    deleted_set = set(deleted_paths)
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 更新 posts 表的 media 和 repost_media 字段
    updated_posts = 0
    updated_posts += _update_media_field(cursor, "posts", "media", "mid", deleted_set, dry_run)
    updated_posts += _update_media_field(cursor, "posts", "repost_media", "mid", deleted_set, dry_run)

    # 更新 comments 表的 local_images 字段
    updated_comments = 0
    cursor.execute("SELECT comment_id, local_images FROM comments WHERE local_images IS NOT NULL")

    for comment_id, local_images_json in cursor.fetchall():
        if not local_images_json:
            continue

        try:
            local_images = json.loads(local_images_json)
            if not isinstance(local_images, list):
                continue

            new_images = [p for p in local_images if p not in deleted_set]
            if len(new_images) == len(local_images):
                continue

            removed = set(local_images) - set(new_images)
            for p in removed:
                print(f"[更新] comments.local_images comment_id={comment_id}: 移除 {p}")

            if not dry_run:
                cursor.execute(
                    "UPDATE comments SET local_images = ? WHERE comment_id = ?",
                    (json.dumps(new_images, ensure_ascii=False) if new_images else None, comment_id)
                )
            updated_comments += 1
        except json.JSONDecodeError:
            pass

    if not dry_run:
        conn.commit()

    conn.close()
    print(f"\n[统计] 更新了 {updated_posts} 条微博记录，{updated_comments} 条评论记录")


def delete_files(files_to_delete: list, dry_run: bool = False):
    """删除文件"""
    deleted_count = 0
    for item in files_to_delete:
        filepath = item["filepath"]
        if dry_run:
            print(f"[模拟] 将删除: {filepath}")
        else:
            try:
                os.remove(filepath)
                print(f"[删除] {filepath}")
                deleted_count += 1
            except Exception as e:
                print(f"[错误] 无法删除 {filepath}: {e}")

    if not dry_run:
        print(f"\n[统计] 删除了 {deleted_count} 个文件")


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("图片清理脚本")
    print("=" * 60)
    print(f"数据库路径: {DATABASE_PATH}")
    print(f"图片目录: {IMAGES_DIR}")
    print(f"目标 MD5: {PLACEHOLDER_MD5_LIST}")
    print(f"模式: {'模拟运行 (不实际执行)' if dry_run else '实际执行'}")
    print("=" * 60)

    if not PLACEHOLDER_MD5_LIST:
        print("\n[错误] PLACEHOLDER_MD5_LIST 为空，请先配置要删除的 MD5 值")
        sys.exit(1)

    if not dry_run:
        # 备份数据库
        backup_database()
        print()

    # 扫描图片
    print("[步骤 1] 扫描图片目录...")
    files_to_delete = scan_images(dry_run)

    if not files_to_delete:
        print("\n[完成] 没有找到需要清理的图片")
        return

    # 获取相对路径列表
    deleted_paths = [item["relative_path"] for item in files_to_delete]

    # 更新数据库
    print("\n[步骤 2] 更新数据库...")
    update_database(deleted_paths, dry_run)

    # 删除文件
    print("\n[步骤 3] 删除文件...")
    delete_files(files_to_delete, dry_run)

    print("\n" + "=" * 60)
    if dry_run:
        print("[完成] 模拟运行结束，实际执行请去掉 --dry-run 参数")
    else:
        print("[完成] 清理完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
