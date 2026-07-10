# -*- coding: utf-8 -*-
"""Note Images Storage Service

支持笔记图片上传、存储和访问。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

# 图片存储根目录
_IMAGES_ROOT = Path("./data/notes")

# 允许的图片类型
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# 限制
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_IMAGES_PER_NOTE = 20


def _get_image_dir(user_id: str, note_id: str) -> Path:
    """获取笔记图片存储目录"""
    # 安全检查：防止路径遍历攻击
    if ".." in user_id or "/" in user_id or "\\" in user_id:
        raise ValueError(f"Invalid user_id: {user_id}")
    if ".." in note_id or "/" in note_id or "\\" in note_id:
        raise ValueError(f"Invalid note_id: {note_id}")

    return _IMAGES_ROOT / user_id / note_id


def _generate_filename(original_filename: str) -> str:
    """生成安全的文件名

    格式: image_{timestamp}_{random}.{ext}
    """
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".png"

    timestamp = int(datetime.now().timestamp() * 1000)
    random_suffix = secrets.token_hex(4)

    return f"image_{timestamp}_{random_suffix}{ext}"


async def save_image(
    user_id: str,
    note_id: str,
    file: UploadFile,
) -> str:
    """保存图片

    Args:
        user_id: 用户 ID
        note_id: 笔记 ID
        file: 上传的文件对象

    Returns:
        图片 URL 路径（相对路径）

    Raises:
        ValueError: 文件类型或大小不符合要求
    """
    # 验证文件类型
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"Unsupported file type: {file.content_type}")

    # 分块读取并即时限流（R36）：此前一次性 file.read() 把任意大的请求体
    # 整个读进内存后才校验 5MB，限制形同虚设（content_type 可伪造，
    # Starlette 默认不限请求体大小）——超限时最多驻留 MAX_FILE_SIZE+1MB。
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise ValueError(f"File size exceeds {MAX_FILE_SIZE / 1024 / 1024}MB")
        chunks.append(chunk)
    content = b"".join(chunks)

    # 获取存储目录 / 生成文件名
    image_dir = _get_image_dir(user_id, note_id)
    filename = _generate_filename(file.filename or "image.png")

    # mkdir / glob 计数 / 写盘（最多 5MB）都是同步阻塞 FS 调用，在 async
    # 上传处理器里会阻塞整个事件循环，卸载到线程池执行（R11 同类，R50）。
    def _persist() -> None:
        image_dir.mkdir(parents=True, exist_ok=True)
        # 检查图片数量限制
        existing_images = list(image_dir.glob("image_*"))
        if len(existing_images) >= MAX_IMAGES_PER_NOTE:
            raise ValueError(f"Maximum {MAX_IMAGES_PER_NOTE} images per note")
        file_path = image_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)

    await asyncio.to_thread(_persist)

    # 返回 URL 路径
    return f"/api/notes/images/{user_id}/{note_id}/{filename}"


def get_image_path(user_id: str, note_id: str, filename: str) -> Optional[Path]:
    """获取图片文件路径

    Args:
        user_id: 用户 ID
        note_id: 笔记 ID
        filename: 文件名

    Returns:
        文件路径，如果不存在返回 None
    """
    # 安全检查
    if ".." in filename or "/" in filename or "\\" in filename:
        return None

    image_dir = _get_image_dir(user_id, note_id)
    file_path = image_dir / filename

    if file_path.exists() and file_path.is_file():
        return file_path

    return None


def list_images(user_id: str, note_id: str) -> list[dict[str, any]]:
    """列出笔记的所有图片

    Args:
        user_id: 用户 ID
        note_id: 笔记 ID

    Returns:
        图片信息列表
    """
    image_dir = _get_image_dir(user_id, note_id)

    if not image_dir.exists():
        return []

    result = []
    for img_path in sorted(image_dir.glob("image_*")):
        if img_path.is_file():
            stat = img_path.stat()
            result.append({
                "filename": img_path.name,
                "url": f"/api/notes/images/{user_id}/{note_id}/{img_path.name}",
                "size": stat.st_size,
                # UTC aware（与 research_notes 的 created_at/updated_at 同基准）；
                # 裸 fromtimestamp 是 naive 本地时间，东八区比笔记时间戳快 8 小时
                "uploaded_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })

    return result


def delete_image(user_id: str, note_id: str, filename: str) -> bool:
    """删除图片

    Args:
        user_id: 用户 ID
        note_id: 笔记 ID
        filename: 文件名

    Returns:
        删除是否成功
    """
    file_path = get_image_path(user_id, note_id, filename)

    if file_path and file_path.exists():
        file_path.unlink()
        return True

    return False


def delete_all_images(user_id: str, note_id: str) -> int:
    """删除笔记的所有图片

    Args:
        user_id: 用户 ID
        note_id: 笔记 ID

    Returns:
        删除的图片数量
    """
    image_dir = _get_image_dir(user_id, note_id)

    if not image_dir.exists():
        return 0

    count = 0
    for img_path in image_dir.glob("image_*"):
        if img_path.is_file():
            img_path.unlink()
            count += 1

    # 删除空目录
    try:
        image_dir.rmdir()
    except OSError:
        pass

    return count


__all__ = [
    "save_image",
    "get_image_path",
    "list_images",
    "delete_image",
    "delete_all_images",
    "MAX_FILE_SIZE",
    "MAX_IMAGES_PER_NOTE",
]
