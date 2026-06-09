# Phase 4.2 - Day 4: Research Notebook 后端实施总结

## 完成时间
2026-06-08

## 实施范围
Research Notes 后端基础（笔记 CRUD + 图片上传 + API 路由）

---

## ✅ 后端实施

### 1. 笔记存储服务
**文件**: `backend/services/research_notes.py`

**数据库**: `./data/research_notes.db` (SQLite WAL 模式)

**表结构**:
```sql
CREATE TABLE research_notes (
    note_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ticker TEXT,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    tags_json TEXT DEFAULT '[]',
    deleted INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 索引
CREATE INDEX idx_notes_session_ticker ON research_notes(session_id, ticker, updated_at DESC) WHERE deleted = 0;
CREATE INDEX idx_notes_user ON research_notes(user_id, updated_at DESC) WHERE deleted = 0;
```

**核心函数**:
- `create_note()`: 创建笔记，返回 note_id
- `update_note()`: 更新标题/内容/标签/ticker（可选参数）
- `delete_note()`: 软删除（标记 deleted=1）
- `get_note()`: 获取单条笔记
- `list_notes()`: 列表查询（支持 ticker 筛选、分页）
- `search_notes()`: 全文搜索（标题 + 内容）

**特性**:
- **软删除机制**: deleted 标记，可恢复
- **按更新时间倒序**: 最新编辑的笔记排在前面
- **Session 隔离**: 不同 session 的笔记互不干扰
- **分页支持**: limit + offset

### 2. 图片存储服务
**文件**: `backend/services/note_images.py`

**存储路径**: `./data/notes/{user_id}/{note_id}/image_{timestamp}_{random}.{ext}`

**限制**:
- **文件类型**: PNG, JPEG, GIF, WebP
- **单文件大小**: 5MB
- **每笔记上限**: 20 张图片

**核心函数**:
- `save_image()`: 异步保存上传的图片，返回 URL
- `get_image_path()`: 获取图片文件路径（用于 FileResponse）
- `list_images()`: 列出笔记的所有图片
- `delete_image()`: 删除单张图片
- `delete_all_images()`: 删除笔记的所有图片

**安全特性**:
- **路径遍历防护**: 验证 user_id/note_id/filename 不含 `..` / `/` / `\`
- **文件类型白名单**: 只允许图片 MIME 类型
- **文件名随机化**: 防止文件名冲突和猜测

### 3. API 路由
**文件**: `backend/api/research_notes_router.py`

**端点列表** (8 个):

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/research-notes` | 创建笔记 |
| GET | `/api/research-notes` | 列出/搜索笔记 |
| GET | `/api/research-notes/{note_id}` | 获取单条笔记 |
| PUT | `/api/research-notes/{note_id}` | 更新笔记 |
| DELETE | `/api/research-notes/{note_id}` | 删除笔记 |
| POST | `/api/research-notes/{note_id}/images` | 上传图片 |
| GET | `/api/notes/images/{user_id}/{note_id}/{filename}` | 获取图片（静态文件） |
| GET | `/api/research-notes/{note_id}/images` | 列出笔记图片 |
| DELETE | `/api/research-notes/{note_id}/images/{filename}` | 删除图片 |

**依赖注入**:
```python
@dataclass(frozen=True)
class ResearchNotesRouterDeps:
    resolve_thread_id: Callable[[Optional[str]], str]
```

**身份验证**:
- 所有端点需要 JWT token (`get_current_user`)
- 权限检查：只能访问自己的笔记和图片
- `require_matching_identity` 验证 user_id 匹配

**请求模型**:
```python
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
```

### 4. 主应用集成
**文件**: `backend/api/main.py`

**注册代码**:
```python
from backend.api.research_notes_router import ResearchNotesRouterDeps, create_research_notes_router

research_notes_router = create_research_notes_router(
    ResearchNotesRouterDeps(
        resolve_thread_id=_resolve_thread_id,
    )
)

app.include_router(research_notes_router)
```

---

## ✅ 测试验证

### 单元测试
**文件**: `backend/tests/test_research_notes.py`

**测试覆盖** (5/5 通过):
1. ✅ `test_create_and_get_note` — 创建和获取笔记
2. ✅ `test_update_note` — 更新标题、内容、标签
3. ✅ `test_delete_note` — 软删除 + 重复删除验证
4. ✅ `test_list_notes` — 列表查询 + ticker 筛选
5. ✅ `test_search_notes` — 全文搜索（标题 + 内容）

**运行结果**:
```
5 passed in 0.24s
```

**测试策略**:
- 使用项目实际数据库（避免 Windows SQLite WAL 锁问题）
- 测试后自动清理数据（`finally` 块调用 `delete_note`）
- 使用 `pytest_session` / `pytest_user` 标识测试数据

---

## 📊 代码统计

| 文件类型 | 新增文件 | 修改文件 | 总代码行数 |
|---------|---------|---------|-----------|
| 后端 Python | 3 个 | 1 个 | ~680 行 |
| 测试文件 | 1 个 | 0 个 | ~130 行 |
| **总计** | **4 个** | **1 个** | **~810 行** |

---

## 🎯 功能亮点

### 1. 软删除设计
笔记删除不物理删除记录，只标记 `deleted=1`，支持未来恢复功能。

### 2. 路径遍历防护
所有涉及文件路径的操作都验证参数不含 `..` / `/` / `\`，防止攻击。

### 3. 图片 URL 自动生成
上传图片后返回完整 URL（`/api/notes/images/...`），前端可直接插入 Markdown。

### 4. 权限检查完整
每个端点都验证：
- JWT token 有效性
- user_id 匹配
- 笔记/图片归属权

### 5. 异步文件上传
使用 `async def` + `await file.read()` 支持高并发上传。

### 6. 搜索功能
支持标题和内容全文搜索（SQLite `LIKE`），便于用户快速定位笔记。

---

## 🔄 API 使用示例

### 1. 创建笔记
```bash
curl -X POST http://localhost:8000/api/research-notes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "user_id": "user_123",
    "title": "AAPL Q1 财报分析",
    "content": "# 要点\n\n营收增长 10%",
    "ticker": "AAPL",
    "tags": ["财报", "科技"]
  }'
```

### 2. 上传图片
```bash
curl -X POST http://localhost:8000/api/research-notes/note_abc/images \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@screenshot.png"
```

返回:
```json
{
  "success": true,
  "url": "/api/notes/images/user_123/note_abc/image_1717891234567_a1b2c3d4.png"
}
```

### 3. 在 Markdown 中引用图片
```markdown
# 财报截图

![Q1营收](/api/notes/images/user_123/note_abc/image_1717891234567_a1b2c3d4.png)
```

### 4. 搜索笔记
```bash
curl "http://localhost:8000/api/research-notes?session_id=test_session&user_id=user_123&q=财报" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 📝 注意事项

### 1. 图片存储
- 图片存储在文件系统（非数据库 BLOB）
- 删除笔记时自动删除关联图片
- 图片路径需确保 `data/notes/` 目录有写权限

### 2. 文件大小限制
- 单文件 5MB（`MAX_FILE_SIZE`）
- 可根据需求调整（需同时更新前端验证）

### 3. 软删除清理
- 当前软删除数据不自动清理
- 建议后续添加定时任务清理 90 天前的 deleted 记录

### 4. 图片 CDN
- 当前通过 FastAPI FileResponse 直接返回
- 生产环境建议使用 CDN（S3 + CloudFront）

### 5. Markdown 渲染
- 后端不渲染 Markdown（纯存储）
- 前端负责 Markdown → HTML 转换

---

## 🔜 下一步（Day 5-6）

### Day 5: 前端实现
1. ✅ TypeScript 类型定义
2. ✅ API Client 方法
3. ✅ Markdown 编辑器组件（工具栏 + 实时预览）
4. ✅ 图片上传组件（拖拽 + 粘贴）
5. ✅ 笔记列表页
6. ✅ 笔记编辑页
7. ✅ 路由配置

### Day 6: 集成与测试
1. ✅ Dashboard 集成（显示当前 ticker 笔记）
2. ✅ E2E 测试（创建/编辑/删除/上传图片）
3. ✅ 用户体验优化（自动保存、加载状态）

---

## ✅ 验收标准

- [x] 笔记 CRUD 功能完整
- [x] 图片上传/下载/删除正常
- [x] 单元测试 5/5 通过
- [x] API 身份验证和权限检查
- [x] 路径遍历攻击防护
- [x] 软删除机制
- [x] 搜索功能
- [x] 注册到主应用

---

**完成状态**: ✅ Day 4 后端全部完成  
**下一步**: Day 5 — 前端 Markdown 编辑器 + 笔记列表/编辑页
