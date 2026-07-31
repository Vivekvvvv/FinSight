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


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-image"

VALID_IMAGES = (
    ("image/png", "x.png", PNG_BYTES, ".png"),
    ("image/jpeg", "x.jpeg", b"\xff\xd8\xff\xe0test-image", ".jpg"),
    ("image/gif", "x.gif", b"GIF89atest-image", ".gif"),
    ("image/webp", "x.webp", b"RIFF\x04\x00\x00\x00WEBPtest-image", ".webp"),
)


def _make_upload(data: bytes, *, content_type: str = "image/png", filename: str = "x.png") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(data),
        headers=Headers({"content-type": content_type}),
    )


def test_save_image_writes_file(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)

    url = asyncio.run(note_images.save_image("alice", "note1", _make_upload(PNG_BYTES)))

    assert url == f"/api/notes/images/alice/note1/{url.rsplit('/', 1)[-1]}"
    written = list((tmp_path / "alice" / "note1").glob("image_*"))
    assert len(written) == 1
    assert written[0].read_bytes() == PNG_BYTES


@pytest.mark.parametrize(("content_type", "filename", "data", "expected_suffix"), VALID_IMAGES)
def test_save_image_accepts_supported_signatures(
    tmp_path,
    monkeypatch,
    content_type,
    filename,
    data,
    expected_suffix,
):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)

    url = asyncio.run(
        note_images.save_image(
            "alice",
            "note1",
            _make_upload(data, content_type=content_type, filename=filename),
        )
    )

    assert url.endswith(expected_suffix)


def test_save_image_uses_verified_type_for_extension(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)

    url = asyncio.run(
        note_images.save_image(
            "alice",
            "note1",
            _make_upload(PNG_BYTES, filename="misleading.jpg"),
        )
    )

    assert url.endswith(".png")


def test_save_image_rejects_bad_content_type(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)

    with pytest.raises(ValueError):
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(b"x", content_type="application/pdf")))


def test_save_image_rejects_spoofed_image_content_type(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)

    with pytest.raises(ValueError):
        asyncio.run(
            note_images.save_image(
                "alice",
                "note1",
                _make_upload(b"<html><script>alert(1)</script></html>"),
            )
        )


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
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(PNG_BYTES)))
    with pytest.raises(ValueError):
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(PNG_BYTES)))


def test_save_image_count_limit_is_atomic_under_concurrency(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)
    monkeypatch.setattr(note_images, "MAX_IMAGES_PER_NOTE", 1)

    async def upload_twice():
        return await asyncio.gather(
            note_images.save_image("alice", "note1", _make_upload(PNG_BYTES)),
            note_images.save_image("alice", "note1", _make_upload(PNG_BYTES)),
            return_exceptions=True,
        )

    results = asyncio.run(upload_twice())

    assert sum(isinstance(item, str) for item in results) == 1
    assert sum(isinstance(item, ValueError) for item in results) == 1
    assert len(list((tmp_path / "alice" / "note1").glob("image_*"))) == 1


def test_save_image_cleans_temp_file_when_atomic_replace_fails(tmp_path, monkeypatch):
    from backend.services import note_images

    monkeypatch.setattr(note_images, "_get_image_dir", lambda u, n: tmp_path / u / n)
    monkeypatch.setattr(
        note_images.os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        asyncio.run(note_images.save_image("alice", "note1", _make_upload(PNG_BYTES)))

    image_dir = tmp_path / "alice" / "note1"
    assert list(image_dir.iterdir()) == []
