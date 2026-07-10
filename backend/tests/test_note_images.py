# -*- coding: utf-8 -*-
"""R50 回归：note 图片保存把同步 FS IO 卸载到线程池后行为不变。

save_image 是 async 上传处理器，mkdir/glob/写盘（最多 5MB）此前直接在
事件循环上同步执行会阻塞所有请求；改为 asyncio.to_thread。本测试锁定
功能语义（保存成功 / 超大小拒绝 / 超数量拒绝）在重构后保持不变。
"""
from __future__ import annotations

import asyncio
import io

import pytest
from starlette.datastructures import Headers, UploadFile


def _make_upload(data: bytes, *, content_type: str = "image/png", filename: str = "x.png") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(data),
        headers=Headers({"content-type": content_type}),
    )


def test_save_image_writes_file(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)

    url = asyncio.run(note_images.save_image("alice", "note1", _make_upload(b"hello-bytes")))

    assert url == f"/api/notes/images/alice/note1/{url.rsplit('/', 1)[-1]}"
    written = list((tmp_path / "alice" / "note1").glob("image_*"))
    assert len(written) == 1
    assert written[0].read_bytes() == b"hello-bytes"


def test_save_image_rejects_bad_content_type(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)

    with pytest.raises(ValueError):
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(b"x", content_type="application/pdf")))


def test_save_image_rejects_oversized(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)
    monkeypatch.setattr(note_images, "MAX_FILE_SIZE", 8)

    with pytest.raises(ValueError):
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(b"x" * 64)))


def test_save_image_rejects_over_count(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)
    monkeypatch.setattr(note_images, "MAX_IMAGES_PER_NOTE", 2)

    for _ in range(2):
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(b"data")))
    with pytest.raises(ValueError):
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(b"data")))
