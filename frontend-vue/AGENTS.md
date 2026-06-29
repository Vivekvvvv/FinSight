# frontend-vue 架构说明

当前前端主线是 Vue 3 + Pinia + Vue Router + ECharts，负责把 FastAPI 提供的研究、报告、时间线、风险和对话能力组织成一个金融终端式工作台。

## 目录骨架

```text
frontend-vue/
  public/
    logo.svg              # FinSight 公共 Logo 与 favicon 来源
  src/
    api/                  # 后端 API 类型与调用封装
    components/           # 可复用展示组件；状态反馈组件集中放在这里
    pages/                # 路由页面
    router/               # 页面路由
    stores/               # 全局状态：身份、主题，以及少量兼容状态
    utils/                # 前端内部工具函数，避免页面重复包装错误与格式化逻辑
    styles/               # 全局设计 token 与 Tailwind 入口
```

## 关键边界

- `src/stores/theme.ts` 是主题单一真相源，负责 `dark | light | system`、本地持久化和根节点 `data-theme`。
- `src/styles/tokens.css` 是视觉 token 层，页面和组件应优先使用 `--fin-*` 变量，不再硬编码大面积背景、文字、边框和状态色。
- `src/components/AppShell.vue` 是应用框架层，只处理导航、顶栏、上下文抽屉和主内容承载，不写具体业务规则。
- `src/components/ThemeToggle.vue` 只负责主题切换 UI，不复制主题解析逻辑。
- `src/components/StatusBanner.vue`、`EmptyState.vue`、`LoadingState.vue`、`ActionButton.vue` 是 7 个核心页面共用的反馈层：只展示状态和按钮交互，不持有业务数据。
- `src/utils/error.ts` 负责把接口/网络错误转成中文可行动提示，技术错误保留到控制台，页面不直接暴露原始异常。
- `src/pages/*` 是业务编排层，调用 `apiClient` 获取数据，把结果传给组件展示。

## 设计原则

- 主题、身份这类横切状态放在 `stores/`，避免页面间重复实现；未接入主线的商业化空壳不要保留在页面或组件目录。
- 页面应填满 `workspace-main` 的可用宽度；需要窄阅读宽度时只限制具体正文块，不限制整页根容器。
- 交易相关文案只能输出研究复查建议，不输出买入、卖出或收益承诺。
- 新增视觉组件必须先复用 `tokens.css`，除图表 palette 外不要散落孤立色值。
- 所有异步按钮必须有 loading/disabled 反馈；空状态、错误状态优先复用共享状态组件，避免每个页面各写一套。

## 变更记录

- 2026-06-29：移除未被路由和组件树引用的套餐/升级空壳组件，当前前端只保留 7 个核心研究入口。
- 2026-06-22：抽取统一反馈组件与错误包装，覆盖 7 个核心入口的 loading、empty、error 和异步按钮反馈；移动端底部导航与弹窗/抽屉增加安全高度约束。
