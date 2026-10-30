# Workmates 高仿真交互原型

以浏览器中打开的 Doubao Workmates 工作台为视觉参考，复刻侧栏导航、伙伴卡片、快捷任务、任务列表与新建任务布局。使用通用演示数据与本地 SVG 头像。

## 启动

需要 Node.js 20+，无需安装依赖。

```sh
cd workmates-prototype
npm run dev
```

打开 http://127.0.0.1:4173 。语法检查：`npm run check`。

## 可体验的流程

- Home：伙伴卡片、快捷任务、任务搜索和筛选、置顶、重命名、归档和恢复。
- New Task：伙伴与项目选择、能力和模型选项、附件文件名、发送任务、演示结果及追问。
- Workmate Details：指令、能力、工作上下文、基本信息编辑和演示连接。
- Automations：创建周期任务配置、暂停与恢复演示状态。
- Projects：创建项目、查看关联任务、从项目发起任务。
- Library：类型筛选、文件预览、Markdown 下载。
- Hub / Code：伙伴检索与分类、编程任务入口。
- 全局搜索：⌘/Ctrl K；发送任务：⌘/Ctrl Enter；关闭弹窗：Esc。

演示数据保存在浏览器 localStorage（`workmates-prototype-v1`）中。不会连接真实飞书、调用 AI 模型或运行定时任务。附件仅记录文件名；模型和能力仅保存为演示配置；文档下载为 Markdown。

## 文件

`dist/` 是可直接静态托管的成品；`app.js` 处理页面和交互，`data.js` 提供演示数据，`secondary.js` 提供辅助页面，`style.css` 与 `secondary.css` 定义样式，`icons.js` 和 `assets/` 提供图标头像。

## 验证

已通过 JavaScript 语法检查，以及浏览器中的任务提交、伙伴创建与详情、自动化创建与暂停、全局搜索、项目任务关联、文件预览流程。已检查桌面和 390px 移动宽度，控制台未发现运行错误。
