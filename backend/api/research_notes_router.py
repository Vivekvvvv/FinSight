# -*- coding: utf-8 -*-
"""Research Notes API Router"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.demo_mode import demo_notes, is_demo_mode
from backend.services import note_images, research_notes


@dataclass(frozen=True)
class ResearchNotesRouterDeps:
    """Research Notes 路由依赖注入"""
    resolve_thread_id: Callable[[Optional[str]], str]


def _provided_user_id(value: str | None) -> str | None:
    """标准化 user_id"""
    text = str(value or "").strip()
    return None if text in {"", "default_user"} else text


# ── Pydantic Models ──


class CreateNoteRequest(BaseModel):
    session_id: str
    user_id: str = "default_user"
    title: str
    content: str = ""
    ticker: Optional[str] = None
    tags: list[str] = []


class UpdateNoteRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    ticker: Optional[str] = None
    tags: Optional[list[str]] = None


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
            require_matching_identity(
                principal=current_user,
                provided=_provided_user_id(req.user_id),
                expected=current_user.user_id,
                field_name="user_id",
            )
            normalized_session = deps.resolve_thread_id(req.session_id)

            # 创建笔记
            note_id = research_notes.create_note(
                session_id=normalized_session,
                user_id=req.user_id,
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
            return {
                "success": False,
                "error": str(exc),
            }

    @router.get("/api/research-notes")
    async def list_notes(
        session_id: str,
        user_id: str = "default_user",
        ticker: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        current_user: Principal = Depends(get_current_user),
    ):
        """列出研究笔记"""
        try:
            # 身份校验
            require_matching_identity(
                principal=current_user,
                provided=_provided_user_id(user_id),
                expected=current_user.user_id,
                field_name="user_id",
            )
            normalized_session = deps.resolve_thread_id(session_id)

            # 搜索或列表
            if q:
                notes = research_notes.search_notes(
                    session_id=normalized_session,
                    user_id=user_id,
                    query=q,
                    limit=limit,
                )
            else:
                notes = research_notes.list_notes(
                    session_id=normalized_session,
                    user_id=user_id,
                    ticker=ticker,
                    limit=limit,
                    offset=offset,
                )
            if is_demo_mode() and not notes and not q:
                notes = demo_notes(normalized_session, user_id, ticker=ticker, limit=limit)

            return {
                "success": True,
                "notes": notes,
                "count": len(notes),
            }

        except HTTPException:
            raise
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "notes": [],
            }

    @router.get("/api/research-notes/{note_id}")
    async def get_note(
        note_id: str,
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
            return {
                "success": False,
                "error": str(exc),
            }

    @router.put("/api/research-notes/{note_id}")
    async def update_note(
        note_id: str,
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
            return {
                "success": False,
                "error": str(exc),
            }

    @router.delete("/api/research-notes/{note_id}")
    async def delete_note(
        note_id: str,
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
            return {
                "success": False,
                "error": str(exc),
            }

    # ── Image Endpoints ──

    @router.post("/api/research-notes/{note_id}/images")
    async def upload_image(
        note_id: str,
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
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    @router.get("/api/notes/images/{user_id}/{note_id}/{filename}")
    async def get_image(
        user_id: str,
        note_id: str,
        filename: str,
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
                media_type="image/png",  # 浏览器会根据实际内容自动识别
            )

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/api/research-notes/{note_id}/images")
    async def list_note_images(
        note_id: str,
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
            return {
                "success": False,
                "error": str(exc),
                "images": [],
            }

    @router.delete("/api/research-notes/{note_id}/images/{filename}")
    async def delete_image(
        note_id: str,
        filename: str,
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
            return {
                "success": False,
                "error": str(exc),
            }

    @router.get("/api/research-notes/semantic-search")
    async def semantic_search(
        session_id: str,
        user_id: str,
        q: str,
        limit: int = 10,
        current_user: Principal = Depends(get_current_user),
    ):
        """
        语义搜索笔记（向量相似度）

        - **q**: 搜索问题，如"关于茅台的估值笔记"
        - **limit**: 返回数量（最大20）
        - 向量服务不可用时自动降级为关键词搜索
        """
        # 权限验证：确保用户只能搜索自己的笔记
        require_matching_identity(current_user, session_id, user_id)

        try:
            from backend.services.notes_rag import semantic_search_notes
            results = semantic_search_notes(
                session_id=session_id,
                user_id=user_id,
                query=q,
                limit=min(limit, 20),
            )
            return {"results": results, "query": q, "total": len(results)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post("/api/research-notes/vectorize-all")
    async def vectorize_all(
        session_id: str,
        user_id: str,
        current_user: Principal = Depends(get_current_user),
    ):
        """批量向量化所有未向量化的笔记"""
        try:
            from backend.services.notes_rag import vectorize_all_notes
            stats = vectorize_all_notes(session_id=session_id, user_id=user_id)
            return {"success": True, **stats}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
