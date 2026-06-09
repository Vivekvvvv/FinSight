<script setup lang="ts">
import { ref, computed, watch } from 'vue';

interface Props {
  modelValue: string;
  placeholder?: string;
  readonly?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '输入 Markdown 内容...',
  readonly: false,
});

const emit = defineEmits<{
  'update:modelValue': [value: string];
  'image-upload': [file: File];
}>();

const localContent = ref(props.modelValue);
const textarea = ref<HTMLTextAreaElement | null>(null);
const showPreview = ref(false);

watch(() => props.modelValue, (newVal) => {
  if (newVal !== localContent.value) {
    localContent.value = newVal;
  }
});

watch(localContent, (newVal) => {
  emit('update:modelValue', newVal);
});

// Markdown 工具栏操作
function insertMarkdown(before: string, after: string = '', placeholder: string = '') {
  if (!textarea.value || props.readonly) return;

  const start = textarea.value.selectionStart;
  const end = textarea.value.selectionEnd;
  const selectedText = localContent.value.substring(start, end) || placeholder;
  const newText = before + selectedText + after;

  localContent.value =
    localContent.value.substring(0, start) +
    newText +
    localContent.value.substring(end);

  // 重新聚焦并选中插入的内容
  setTimeout(() => {
    textarea.value?.focus();
    textarea.value?.setSelectionRange(start + before.length, start + before.length + selectedText.length);
  }, 0);
}

function insertBold() {
  insertMarkdown('**', '**', '粗体文本');
}

function insertItalic() {
  insertMarkdown('*', '*', '斜体文本');
}

function insertHeading() {
  insertMarkdown('## ', '', '标题');
}

function insertList() {
  insertMarkdown('- ', '', '列表项');
}

function insertLink() {
  insertMarkdown('[', '](https://example.com)', '链接文本');
}

function insertCode() {
  insertMarkdown('`', '`', '代码');
}

function insertCodeBlock() {
  insertMarkdown('```\n', '\n```', '代码块');
}

// 图片上传
function handleImageUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) {
    emit('image-upload', file);
    input.value = ''; // 清空input以允许重复上传同一文件
  }
}

function triggerImageUpload() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/png,image/jpeg,image/gif,image/webp';
  input.onchange = handleImageUpload;
  input.click();
}

// 拖拽上传
function handleDrop(event: DragEvent) {
  event.preventDefault();
  if (props.readonly) return;

  const file = event.dataTransfer?.files[0];
  if (file && file.type.startsWith('image/')) {
    emit('image-upload', file);
  }
}

function handleDragOver(event: DragEvent) {
  event.preventDefault();
}

// 粘贴上传
function handlePaste(event: ClipboardEvent) {
  if (props.readonly) return;

  const items = event.clipboardData?.items;
  if (!items) return;

  for (let i = 0; i < items.length; i++) {
    if (items[i].type.startsWith('image/')) {
      const file = items[i].getAsFile();
      if (file) {
        event.preventDefault();
        emit('image-upload', file);
        break;
      }
    }
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeUrl(value: string): string {
  const text = value.trim();
  if (/^(https?:|\/api\/|data:image\/)/i.test(text)) return text;
  return '#';
}

// 简单的 Markdown 预览（仅支持基本格式，先转义 HTML 再转换）
const previewHtml = computed(() => {
  let html = escapeHtml(localContent.value);

  // 标题
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // 粗体和斜体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // 链接
  html = html.replace(/\[(.+?)\]\((.+?)\)/g, (_match, label, url) => {
    return `<a href="${safeUrl(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });

  // 图片
  html = html.replace(/!\[(.+?)\]\((.+?)\)/g, (_match, alt, url) => {
    return `<img src="${safeUrl(url)}" alt="${alt}" style="max-width: 100%; height: auto;" />`;
  });

  // 代码
  html = html.replace(/`(.+?)`/g, '<code>$1</code>');

  // 列表
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

  // 段落
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';

  return html;
});
</script>

<template>
  <div class="markdown-editor">
    <!-- 工具栏 -->
    <div v-if="!readonly" class="toolbar bg-gray-100 border border-gray-300 rounded-t px-2 py-1 flex gap-1">
      <button @click="insertBold" class="toolbar-btn" title="粗体">
        <strong>B</strong>
      </button>
      <button @click="insertItalic" class="toolbar-btn" title="斜体">
        <em>I</em>
      </button>
      <button @click="insertHeading" class="toolbar-btn" title="标题">
        H
      </button>
      <span class="border-l border-gray-400 mx-1"></span>
      <button @click="insertList" class="toolbar-btn" title="列表">
        •
      </button>
      <button @click="insertLink" class="toolbar-btn" title="链接">
        🔗
      </button>
      <button @click="insertCode" class="toolbar-btn" title="代码">
        &lt;/&gt;
      </button>
      <button @click="insertCodeBlock" class="toolbar-btn" title="代码块">
        { }
      </button>
      <span class="border-l border-gray-400 mx-1"></span>
      <button @click="triggerImageUpload" class="toolbar-btn" title="上传图片">
        🖼️
      </button>
      <span class="border-l border-gray-400 mx-1"></span>
      <button @click="showPreview = !showPreview" class="toolbar-btn" :class="{ 'bg-blue-100': showPreview }" title="预览">
        👁️
      </button>
    </div>

    <!-- 编辑区 -->
    <div class="editor-container" :class="{ 'split-view': showPreview }">
      <textarea
        ref="textarea"
        v-model="localContent"
        :placeholder="placeholder"
        :readonly="readonly"
        class="editor-textarea"
        @drop="handleDrop"
        @dragover="handleDragOver"
        @paste="handlePaste"
      ></textarea>

      <!-- 预览区 -->
      <div v-if="showPreview" class="preview-pane" v-html="previewHtml"></div>
    </div>
  </div>
</template>

<style scoped>
.markdown-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
}

.toolbar-btn {
  padding: 4px 8px;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.toolbar-btn:hover {
  background: #f3f4f6;
}

.editor-container {
  display: flex;
  gap: 1px;
  border: 1px solid #d1d5db;
  border-top: none;
  border-radius: 0 0 4px 4px;
  min-height: 300px;
}

.editor-container.split-view .editor-textarea {
  width: 50%;
  border-right: 1px solid #d1d5db;
}

.editor-textarea {
  width: 100%;
  padding: 12px;
  border: none;
  outline: none;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  min-height: 300px;
}

.preview-pane {
  width: 50%;
  padding: 12px;
  overflow-y: auto;
  background: #fafafa;
  font-size: 14px;
  line-height: 1.6;
}

.preview-pane :deep(h1) {
  font-size: 2em;
  font-weight: bold;
  margin: 0.5em 0;
}

.preview-pane :deep(h2) {
  font-size: 1.5em;
  font-weight: bold;
  margin: 0.5em 0;
}

.preview-pane :deep(h3) {
  font-size: 1.17em;
  font-weight: bold;
  margin: 0.5em 0;
}

.preview-pane :deep(strong) {
  font-weight: bold;
}

.preview-pane :deep(em) {
  font-style: italic;
}

.preview-pane :deep(code) {
  background: #e5e7eb;
  padding: 2px 4px;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', monospace;
}

.preview-pane :deep(ul) {
  list-style: disc;
  margin-left: 1.5em;
}

.preview-pane :deep(a) {
  color: #3b82f6;
  text-decoration: underline;
}
</style>
