# -*- coding: utf-8 -*-
"""Research Notes API Router"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.demo_mode import demo_notes, is_demo_mode
from backend.services import note_images, research_notes

logger = logging.getLogger(__name__)

_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class ResearchNotesRouterDeps:
    """Research Notes 路由依赖注入"""
    resolve_thread_id: Callable[[Optional[str]], str]


def _provided_user_id(value: str | None) -> str | None:
    """标准化 user_id"""
    text = str(value or "").strip()
    return None if text in {"", "default_user"} else text


# ── Pydantic Models ──


NoteTag = Annotated[str, Field(max_length=64)]
NoteIdPath = Annotated[str, Path(min_length=1, max_length=128)]
UserIdPath = Annotated[str, Path(min_length=1, max_length=64)]
ImageFilenamePath = Annotated[str, Path(min_length=1, max_length=255)]


class CreateNoteRequest(BaseModel):
    session_id: str = Field(..., max_length=256)
    user_id: str = Field("default_user", max_length=64)
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field("", max_length=100_000)
    ticker: Optional[str] = Field(None, max_length=32)
    tags: list[NoteTag] = Field(default_factory=list, max_length=20)


class UpdateNoteRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    content: Optional[str] = Field(None, max_length=100_000)
    ticker: Optional[str] = Field(None, max_length=32)
    tags: Optional[list[NoteTag]] = Field(None, max_length=20)


def create_research_notes_router(deps: ResearchNotesRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Research Notes"])

    @router.post("/api/research-notes")
    async def create_note(
        req: CreateNoteRequest,
        current_user: Principal = Depends(get_current_user),
    ):
        """创建研究笔记"""
        try:
            # 身份校验
            provided_user_id = _provided_user_id(req.user_id)
            require_matching_identity(
                principal=current_user,
                provided=provided_user_id,
                expected=current_user.user_id,
                field_name="user_id",
            )
            effective_user_id = provided_user_id or current_user.user_id
            normalized_session = deps.resolve_thread_id(req.session_id)

            # 创建笔记
            note_id = research_notes.create_note(
                session_id=normalized_session,
                user_id=effective_user_id,
                title=req.title,
                content=req.content,
                ticker=req.ticker,
                tags=req.tags,
            )

            return {
                "success": True,
                "note_id": note_id,
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/create] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.get("/api/research-notes")
    async def list_notes(
        session_id: str,
        user_id: str = "default_user",
        ticker: Optional[str] = Query(None, max_length=32),
        q: Optional[str] = Query(None, max_length=2048),
        # 夹紧分页参数，负 offset / 超大 limit 不透传存储层（审计 E4）
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0, le=100000),
        current_user: Principal = Depends(get_current_user),
    ):
        """列出研究笔记"""
        try:
            # 身份校验
            provided_user_id = _provided_user_id(user_id)
            require_matching_identity(
                principal=current_user,
                provided=provided_user_id,
                expected=current_user.user_id,
                field_name="user_id",
            )
            effective_user_id = provided_user_id or current_user.user_id
            normalized_session = deps.resolve_thread_id(session_id)

            # 搜索或列表
            if q:
                notes = research_notes.search_notes(
                    session_id=normalized_session,
                    user_id=effective_user_id,
                    query=q,
                    limit=limit,
                )
            else:
                notes = research_notes.list_notes(
                    session_id=normalized_session,
                    user_id=effective_user_id,
                    ticker=ticker,
                    limit=limit,
                    offset=offset,
                )
            if is_demo_mode() and not notes and not q:
                notes = demo_notes(normalized_session, effective_user_id, ticker=ticker, limit=limit)

            return {
                "success": True,
                "notes": notes,
                "count": len(notes),
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/list] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    # 注意：必须注册在 GET /api/research-notes/{note_id} 之前，
    # 否则 "semantic-search" 会被当作 note_id 匹配而永远 404。
    @router.get("/api/research-notes/semantic-search")
    async def semantic_search(
        session_id: str,
        user_id: str = "default_user",
        q: str = Query("", max_length=2048),
        limit: int = Query(10, ge=1, le=20),
        current_user: Principal = Depends(get_current_user),
    ):
        """
        语义搜索笔记（向量相似度）

        - **q**: 搜索问题，如"关于茅台的估值笔记"
        - **limit**: 返回数量（最大20）
        - 向量服务不可用时自动降级为关键词搜索
        """
        try:
            # 权限验证：确保用户只能搜索自己的笔记
            provided_user_id = _provided_user_id(user_id)
            require_matching_identity(
                principal=current_user,
                provided=provided_user_id,
                expected=current_user.user_id,
                field_name="user_id",
            )
            effective_user_id = provided_user_id or current_user.user_id
            normalized_session = deps.resolve_thread_id(session_id)

            from backend.services.notes_rag import semantic_search_notes
            results = semantic_search_notes(
                session_id=normalized_session,
                user_id=effective_user_id,
                query=q,
                limit=limit,
            )
            return {"results": results, "query": q, "total": len(results)}
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/semantic-search] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.get("/api/research-notes/{note_id}")
    async def get_note(
        note_id: NoteIdPath,
        current_user: Principal = Depends(get_current_user),
    ):
        """获取单条笔记"""
        try:
            note = research_notes.get_note(note_id)

            if not note:
                raise HTTPException(status_code=404, detail="Note not found")

            # 权限检查：只能访问自己的笔记
            if note["user_id"] != current_user.user_id:
                raise HTTPException(status_code=403, detail="Access denied")

            return {
                "success": True,
                "note": note,
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/get] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.put("/api/research-notes/{note_id}")
    async def update_note(
        note_id: NoteIdPath,
        req: UpdateNoteRequest,
        current_user: Principal = Depends(get_current_user),
    ):
        """更新笔记"""
        try:
            # 先获取笔记验证权限
            note = research_notes.get_note(note_id)
            if not note:
                raise HTTPException(status_code=404, detail="Note not found")

            if note["user_id"] != current_user.user_id:
                raise HTTPException(status_code=403, detail="Access denied")

            # 更新笔记
            success = research_notes.update_note(
                note_id=note_id,
                title=req.title,
                content=req.content,
                ticker=req.ticker,
                tags=req.tags,
            )

            return {
                "success": success,
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/update] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.delete("/api/research-notes/{note_id}")
    async def delete_note(
        note_id: NoteIdPath,
        current_user: Principal = Depends(get_current_user),
    ):
        """删除笔记"""
        try:
            # 先获取笔记验证权限
            note = research_notes.get_note(note_id)
            if not note:
                raise HTTPException(status_code=404, detail="Note not found")

            if note["user_id"] != current_user.user_id:
                raise HTTPException(status_code=403, detail="Access denied")

            # 删除笔记
            success = research_notes.delete_note(note_id)

            # 删除关联的图片
            if success:
                note_images.delete_all_images(note["user_id"], note_id)

            return {
                "success": success,
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/delete] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    # ── Image Endpoints ──

    @router.post("/api/research-notes/{note_id}/images")
    async def upload_image(
        note_id: NoteIdPath,
        file: UploadFile = File(...),
        current_user: Principal = Depends(get_current_user),
    ):
        """上传图片到笔记"""
        try:
            # 验证笔记存在和权限
            note = research_notes.get_note(note_id)
            if not note:
                raise HTTPException(status_code=404, detail="Note not found")

            if note["user_id"] != current_user.user_id:
                raise HTTPException(status_code=403, detail="Access denied")

            # 保存图片
            image_url = await note_images.save_image(
                user_id=note["user_id"],
                note_id=note_id,
                file=file,
            )

            return {
                "success": True,
                "url": image_url,
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid image upload") from e
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/upload-image] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.get("/api/notes/images/{user_id}/{note_id}/{filename}")
    async def get_image(
        user_id: UserIdPath,
        note_id: NoteIdPath,
        filename: ImageFilenamePath,
        current_user: Principal = Depends(get_current_user),
    ):
        """获取笔记图片（静态文件）"""
        try:
            # 权限检查：只能访问自己的图片
            if user_id != current_user.user_id:
                raise HTTPException(status_code=403, detail="Access denied")

            # 获取图片路径
            file_path = note_images.get_image_path(user_id, note_id, filename)

            if not file_path:
                raise HTTPException(status_code=404, detail="Image not found")

            # 返回静态文件
            return FileResponse(
                path=file_path,
                media_type=_IMAGE_MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream"),
                headers={"X-Content-Type-Options": "nosniff"},
            )

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/get-image] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.get("/api/research-notes/{note_id}/images")
    async def list_note_images(
        note_id: NoteIdPath,
        current_user: Principal = Depends(get_current_user),
    ):
        """列出笔记的所有图片"""
        try:
            # 验证笔记存在和权限
            note = research_notes.get_note(note_id)
            if not note:
                raise HTTPException(status_code=404, detail="Note not found")

            if note["user_id"] != current_user.user_id:
                raise HTTPException(status_code=403, detail="Access denied")

            # 列出图片
            images = note_images.list_images(note["user_id"], note_id)

            return {
                "success": True,
                "images": images,
                "count": len(images),
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/list-images] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.delete("/api/research-notes/{note_id}/images/{filename}")
    async def delete_image(
        note_id: NoteIdPath,
        filename: ImageFilenamePath,
        current_user: Principal = Depends(get_current_user),
    ):
        """删除笔记图片"""
        try:
            # 验证笔记存在和权限
            note = research_notes.get_note(note_id)
            if not note:
                raise HTTPException(status_code=404, detail="Note not found")

            if note["user_id"] != current_user.user_id:
                raise HTTPException(status_code=403, detail="Access denied")

            # 删除图片
            success = note_images.delete_image(note["user_id"], note_id, filename)

            return {
                "success": success,
            }

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/delete-image] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.post("/api/research-notes/vectorize-all")
    async def vectorize_all(
        session_id: str,
        user_id: str,
        current_user: Principal = Depends(get_current_user),
    ):
        """批量向量化所有未向量化的笔记"""
        try:
            provided_user_id = _provided_user_id(user_id)
            require_matching_identity(
                principal=current_user,
                provided=provided_user_id,
                expected=current_user.user_id,
                field_name="user_id",
            )
            effective_user_id = provided_user_id or current_user.user_id
            normalized_session = deps.resolve_thread_id(session_id)

            from backend.services.notes_rag import vectorize_all_notes
            stats = vectorize_all_notes(session_id=normalized_session, user_id=effective_user_id)
            return {"success": True, **stats}
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[research-notes/vectorize-all] failed")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    return router
