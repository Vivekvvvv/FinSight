# Phase 7 上传与文件系统验证报告

**日期**: 2026-06-08  
**状态**: ✅ **全部通过**

---

## 测试环境

- **后端**: `DEV_MODE=1 uvicorn backend.api.main:app --port 8001`
- **Session**: `public:anonymous:phase7-smoke`
- **User**: `default_user`（DEV_MODE 下 principal.user_id 固定值）

---

## 测试结果

### 1. 创建笔记

```
POST /api/research-notes?session_id=...&user_id=default_user
{ticker: "AAPL", title: "smoke upload test", content: "test upload"}
```

**结果**: ✅ 200，`note_id: note_8bd27cbbcc30`

---

### 2. 上传图片

```
POST /api/research-notes/note_8bd27cbbcc30/images
Content-Type: multipart/form-data
(1x1 PNG, 72 bytes)
```

**结果**: ✅ 200

```json
{
  "success": true,
  "url": "/api/notes/images/default_user/note_8bd27cbbcc30/image_1780928396145_a6b1ab21.png"
}
```

---

### 3. 通过 URL 访问图片

```
GET /api/notes/images/default_user/note_8bd27cbbcc30/image_1780928396145_a6b1ab21.png
```

**结果**: ✅ 200
- `Content-Type: image/png`
- 文件大小: 72 bytes
- 内容与上传一致

---

### 4. 安全性：路径遍历防护

| 攻击路径 | HTTP 状态 | 结果 |
|---------|---------|------|
| `/api/notes/images/default_user/../../etc/passwd` | 404 | ✅ 拦截 |
| `/api/notes/images/default_user/note_xxx/../../../etc/passwd` | 404 | ✅ 拦截 |
| `/api/notes/images/default_user/note_xxx/%2e%2e/%2e%2e/etc/passwd` | 404 | ✅ 拦截 |

---

### 5. 权限验证

DEV_MODE 下 `principal.user_id = "default_user"`。若用其他 user_id 创建笔记，上传图片时会返回 403（Access denied），这是正确的权限检查行为。

---

## 待验证项目（需真实前端）

- [ ] 超大图片（>10MB）拒绝并显示错误提示
- [ ] 非图片文件（.exe, .pdf 等）拒绝并显示错误提示
- [ ] 删除 note 后图片文件是否清理
- [ ] 前端图片预览 UI 是否正常显示

---

## 文件存储路径

图片存储在 `backend/data/note_images/{user_id}/{note_id}/` 目录下：

```
backend/data/note_images/
  default_user/
    note_8bd27cbbcc30/
      image_1780928396145_a6b1ab21.png
```

在 Docker compose 模式下，该目录映射到 `backend_data` 卷（`/app/data/note_images/`）。
