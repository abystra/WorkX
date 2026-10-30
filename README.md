# WorkX

面向个人与组织的 SaaS AI 工作台，支持智能伙伴、项目、知识、任务成果及飞书／企业微信等生态接入。

- [架构文档入口](docs/README.md)：React + TypeScript / Python FastAPI / E2B / Claude Agent SDK 目标架构。
- [个人与组织租户](docs/TENANCY-MODEL.md)：个人拥有独立空间，加入组织不混用数据和凭证。
- [统一凭证方案](docs/CREDENTIAL-SOLUTION.md)：原生 Broker／Gateway、沙箱外密钥，当前不引入 Nango。
- [当前交互原型](workmates-prototype/README.md)：本地运行与体验说明。
- [产品功能清单](workmates-prototype/docs/PRODUCT-FEATURES.md)：当前功能、验收边界和后续范围。

```sh
cd workmates-prototype
npm run dev
```

默认访问 http://127.0.0.1:4173/ 。当前是本地原型；真实后端、Claude 和 E2B 执行按架构文档分阶段建设。
