# Phase 4.2 实施计划：Research Notebook

## 目标
为每个 ticker 提供独立的研究笔记本，支持 Markdown 编辑和图片上传，解决用户"研究资料分散、截图无处存放"的痛点。

---

## 功能需求

### 1. 核心功能
- **笔记 CRUD**: 每个 ticker 可创建多条笔记
- **Markdown 编辑**: 支持标题、列表、链接、代码块
- **图片上传**: 拖拽/粘贴上传截图、图表
- **笔记列表**: 按时间倒序展示，支持搜索和标签筛选
- **关联 ticker**: 笔记与 ticker 绑定，在 Dashboard 页面直接访问

### 2. 扩展需求（Phase 4 Day 4-5）
- **版本历史**: 保留笔记编辑历史（快照对比）
- **笔记模板**: 预设模板（财报分析、行业研究、竞品对比）
- **AI 总结**: 对长笔记生成摘要
- **导出功能**: 导出为 PDF/Markdown 文件

---

## 数据模型

### 笔记表结构
```python
research_notes (
    note_id TEXT PRIMARY KEY,          # uuid
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ticker TEXT,                       # 可选，绑定标的
    title TEXT NOT NULL,
    content TEXT,                      # Markdown 内容
    tags_json TEXT,                    # JSON 数组
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    INDEX(session_id, ticker, updated_at DESC)
)
```

### 图片存储
- **路径**: `./data/notes/{user_id}/{note_id}/image_001.png`
- **元数据**: 存储在笔记 content 中的 Markdown 引用
- **格式支持**: PNG, JPG, GIF, WebP
- **大小限制**: 5MB/图片，最多 20 张/笔记

---

## 后端实施

### 1. 笔记存储服务
**文件**: `backend/services/research_notes.py`

**功能**:
```python
def create_note(
    session_id: str,
    user_id: str,
    title: str,
    content: str = "",
    ticker: str | None = None,
    tags: list[str] = None,
) -> str:
    """创建笔记，返回 note_id"""

def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
) -> bool:
    """更新笔记"""

def delete_note(note_id: str) -> bool:
    """删除笔记（软删除，标记 deleted=1）"""

def get_note(note_id: str) -> dict | None:
    """获取单条笔记"""

def list_notes(
    session_id: str,
    user_id: str,
    ticker: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """列出笔记"""
```

### 2. 图片上传服务
**文件**: `backend/services/note_images.py`

**功能**:
```python
def save_image(
    user_id: str,
    note_id: str,
    file: UploadFile,
) -> str:
    """保存图片，返回图片 URL"""

def list_images(note_id: str) -> list[str]:
    """列出笔记的所有图片"""

def delete_image(user_id: str, note_id: str, filename: str) -> bool:
    """删除图片"""
```

**实现细节**:
- 图片文件名：`image_{timestamp}_{random}.{ext}`
- URL 格式：`/api/notes/images/{user_id}/{note_id}/{filename}`
- 安全检查：验证文件类型、大小、路径遍历攻击

### 3. API 路由
**文件**: `backend/api/research_notes_router.py`

**端点**:
```python
POST   /api/research-notes                # 创建笔记
GET    /api/research-notes?ticker=AAPL    # 列出笔记
GET    /api/research-notes/{note_id}      # 获取单条笔记
PUT    /api/research-notes/{note_id}      # 更新笔记
DELETE /api/research-notes/{note_id}      # 删除笔记

POST   /api/research-notes/{note_id}/images  # 上传图片
GET    /api/notes/images/{user_id}/{note_id}/{filename}  # 获取图片（静态文件）
DELETE /api/research-notes/{note_id}/images/{filename}  # 删除图片
```

---

## 前端实施

### 1. TypeScript 类型
**文件**: `frontend-vue/src/api/types.ts`

```typescript
export interface ResearchNote {
  note_id: string;
  session_id: string;
  user_id: string;
  ticker?: string | null;
  title: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface NoteImage {
  filename: string;
  url: string;
  size: number;
  uploaded_at: string;
}
```

### 2. Markdown 编辑器组件
**文件**: `frontend-vue/src/components/MarkdownEditor.vue`

**功能**:
- **编辑器**: Textarea + 实时预览（split view）
- **工具栏**: 加粗、斜体、标题、列表、链接、代码块
- **图片插入**: 
  - 拖拽上传（dropzone）
  - 粘贴上传（clipboard）
  - 点击按钮选择文件
- **自动保存**: 5 秒无操作后自动保存草稿

**技术选型**:
- 使用 `<textarea>` + 自定义工具栏（轻量，无需第三方库）
- Markdown 渲染：使用 `marked` 库（项目可能已有）
- 图片上传：`multipart/form-data`

### 3. 笔记列表页
**文件**: `frontend-vue/src/pages/ResearchNotesPage.vue`

**布局**:
```
+----------------------------------+
| [+ 新建笔记]   [搜索...]  [标签▼] |
+----------------------------------+
| 笔记卡片 1                        |
| AAPL | 2024 Q1 财报分析          |
| 更新于 2026-06-08 | #财报 #科技   |
+----------------------------------+
| 笔记卡片 2                        |
| NVDA | GPU 需求分析              |
| ...                              |
+----------------------------------+
```

**交互**:
- 点击卡片 → 跳转编辑页
- 右上角操作菜单（编辑/删除）
- 支持按 ticker 筛选

### 4. 笔记编辑页
**文件**: `frontend-vue/src/pages/ResearchNoteEditPage.vue`

**布局**:
```
+----------------------------------+
| [← 返回]  标题：_____________     |
| Ticker: [AAPL▼]  标签: [+]      |
+----------------------------------+
| [B] [I] [H1] [•] [1] [链接] [图] |
+----------------------------------+
| Markdown 编辑区 | 实时预览       |
|                 |                |
|                 |                |
+----------------------------------+
| [上传图片] [保存] [自动保存中...] |
+----------------------------------+
```

### 5. Dashboard 集成
**文件**: `frontend-vue/src/pages/DashboardPage.vue`

**新增模块**: "研究笔记" 标签页

**显示**:
- 当前 ticker 的所有笔记（最多 5 条）
- "查看全部" 按钮跳转到笔记列表（带 ticker 筛选）

---

## 实施步骤

### Day 4: 后端基础（4-5h）
1. ✅ 创建 `research_notes.py` 存储服务
2. ✅ 创建 `note_images.py` 图片服务
3. ✅ 创建 `research_notes_router.py` API 路由
4. ✅ 注册路由到 `main.py`
5. ✅ 单元测试（CRUD + 图片上传）

### Day 5: 前端实现（5-6h）
1. ✅ TypeScript 类型定义
2. ✅ API Client 方法
3. ✅ `MarkdownEditor.vue` 组件
4. ✅ `ResearchNotesPage.vue` 列表页
5. ✅ `ResearchNoteEditPage.vue` 编辑页
6. ✅ 路由配置
7. ✅ Dashboard 集成

### Day 6: 测试与优化（2-3h）
1. ✅ E2E 测试（创建/编辑/删除笔记）
2. ✅ 图片上传测试（拖拽/粘贴）
3. ✅ 性能优化（图片压缩、懒加载）
4. ✅ 用户体验优化（加载状态、错误提示）

---

## 技术细节

### 图片上传流程
1. 前端：用户拖拽/粘贴图片
2. 前端：读取 File 对象，验证类型和大小
3. 前端：上传到 `/api/research-notes/{note_id}/images`
4. 后端：保存到 `data/notes/{user_id}/{note_id}/`
5. 后端：返回图片 URL
6. 前端：在 Markdown 中插入 `![alt](url)`

### Markdown 图片引用格式
```markdown
![财报截图](/api/notes/images/user_123/note_abc/image_001.png)
```

### 安全考虑
1. **路径遍历防护**: 验证 `user_id` 和 `note_id` 格式
2. **文件类型白名单**: 只允许 `image/png|jpeg|gif|webp`
3. **大小限制**: 单文件 5MB，总共 100MB/用户
4. **身份验证**: 所有端点需要 JWT token
5. **权限检查**: 只能访问自己的笔记和图片

---

## 数据库迁移

```sql
-- 创建研究笔记表
CREATE TABLE IF NOT EXISTS research_notes (
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

CREATE INDEX IF NOT EXISTS idx_notes_session_ticker
    ON research_notes(session_id, ticker, updated_at DESC)
    WHERE deleted = 0;

CREATE INDEX IF NOT EXISTS idx_notes_user
    ON research_notes(user_id, updated_at DESC)
    WHERE deleted = 0;
```

---

## 验收标准

### 后端
- [ ] 笔记 CRUD 功能完整
- [ ] 图片上传/下载/删除正常
- [ ] 单元测试覆盖核心逻辑
- [ ] API 身份验证和权限检查

### 前端
- [ ] Markdown 编辑器可用
- [ ] 图片拖拽上传功能
- [ ] 图片粘贴上传功能
- [ ] 笔记列表正常显示
- [ ] 笔记编辑页保存功能
- [ ] Dashboard 集成显示

### E2E
- [ ] 创建笔记流程
- [ ] 编辑笔记流程
- [ ] 上传图片流程
- [ ] 删除笔记流程

---

## 后续扩展

### Phase 4.3+
- **版本历史**: 每次保存记录快照，支持对比查看
- **协作编辑**: 多用户同时编辑（WebSocket 同步）
- **笔记模板**: 预设 5 种模板（财报、行业、竞品、事件、假设）
- **AI 功能**:
  - 根据 Dashboard 数据自动生成笔记草稿
  - 长笔记自动总结（TL;DR）
  - 智能标签建议
- **导出功能**: PDF/Markdown/HTML 导出

---

**预计工时**: 11-14 小时  
**风险点**: 
1. 图片上传安全性需仔细验证
2. Markdown 编辑器体验需多次迭代
3. 大文件上传可能需要分片上传

**依赖**:
- 后端：FastAPI multipart 支持（已有）
- 前端：Markdown 渲染库（建议 `marked` 或 `markdown-it`）
