# WorkX 架构设计文档

版本：0.5 · 2026-10-30 · 状态：目标架构，尚未实施

本目录基于用户提供的分层架构图调整：保留 E2B Sandbox，将 OpenCode Harness 替换为 **Claude Agent SDK + WorkX Runner**。面向企业 SaaS 场景，补齐多租户、任务调度、知识处理、事件流和成果持久化边界。

## 阅读顺序

| 文档 | 解决的问题 |
| --- | --- |
| [总体架构](ARCHITECTURE.md) | 分层、语言职责、依赖关系、业务执行链路 |
| [Claude 与 E2B 执行设计](CLAUDE-E2B-RUNTIME.md) | Harness、Runner、沙箱、会话、权限、恢复 |
| [沙箱文件系统规范](SANDBOX-FILESYSTEM.md) | `/mnt` 路径依据、卷与物化区别、权限及持久化边界 |
| [凭证与 Connector 架构](CREDENTIALS-AND-CONNECTORS.md) | SSO、MCP／Skill／CLI 凭证、短期票据与中间件候选 |
| [凭证落地方案](CREDENTIAL-SOLUTION.md) | 按使用方式分四类、沙箱外注入、Vault 参照模型、飞书 sidecar、分期 |
| [Nango 引入评审](NANGO-ADOPTION.md) | 能否实际引入、认证分流、部署／协议／生产验收门槛 |
| [Skill／MCP 运行配置](SKILL-RUNTIME-CONTRACT.md) | 独立 env、`.env`、Secret 文件、启动与清理契约 |
| [知识解析与搜索选型](KNOWLEDGE-PIPELINE.md) | Tika 解析、Meilisearch 检索、权限与评测路线 |
| [数据与租户设计](DATA-AND-TENANCY.md) | 组织用户角色、领域对象、数据隔离、知识与成果 |
| [接口与事件约定](API-AND-EVENTS.md) | 前后端 API、Runner 协议、状态机、流式事件 |
| [实施路线与验收](IMPLEMENTATION-PLAN.md) | 从当前原型迁移到真实产品的顺序与验证要求 |
| [ADR-0001：执行内核选型](adr/0001-claude-agent-sdk-on-e2b.md) | 这次选型的原因、影响和未决事项 |
| [ADR-0002：凭证注入方式](adr/0002-credential-broker-and-egress-injection.md) | 凭证分类、自建 Broker、沙箱外注入的决定与取舍 |

## 与现有原型的关系

现有 [原型说明](../workmates-prototype/README.md)、[功能清单](../workmates-prototype/docs/PRODUCT-FEATURES.md)、[SaaS 产品基础](../workmates-prototype/docs/SAAS-FOUNDATION.md)、[生态调研](../workmates-prototype/docs/ECOSYSTEM-INTEGRATION-RESEARCH.md) 继续描述当前可体验的功能和产品要求。

当前代码是 `workmates-prototype/dist/` 下的原生 JavaScript 交互原型，使用浏览器 localStorage 和演示执行逻辑。React、FastAPI、Claude、E2B、数据库和知识 Workers 都是本目录中的目标设计；本次仅编写文档，没有迁移前端、部署后端或创建付费沙箱。

## 架构基线

- 前端：React + TypeScript；管理 API：Python 3.12+ + FastAPI。
- 执行：E2B Linux 沙箱内运行 Python WorkX Runner，使用 Claude Agent SDK；Claude 模型通过受控 API 认证调用。
- 异步：独立 Task Worker、Knowledge Worker、Channel Worker；首版选择 Redis Streams 消费组与 PostgreSQL outbox，不在 API 请求内执行长任务。
- 知识：Tika 作为通用解析候选；Meilisearch 自动 Embedding＋混合检索作为优先验证的 SearchProvider 候选，与 pgvector 基线评测，首版不默认叠加双引擎。
- 授权：SSO、外部连接授权、密钥保管和工具票据分层；凭证按使用方式分类，真实值不进沙箱，由自建 Credential Broker 与 Gateway 在沙箱外注入。OpenBao 做加密，Nango 仅作长尾 OAuth Adapter，飞书 CLI 默认在受控 Worker 运行，见 [凭证落地方案](CREDENTIAL-SOLUTION.md)。
- 存储：PostgreSQL + pgvector 起步；S3 兼容对象存储保存文件、成果和恢复材料。Redis 不作为唯一业务事实来源。
- 协议：前端 REST + SSE 为主；WebSocket 留给确有双向实时需求的编辑器或平台连接。
- 安全边界：租户与资源授权由 WorkX 服务端核验；E2B 提供执行环境隔离。SDK 工具权限和提示词不是租户隔离机制。

## 官方资料核对

以下资料于 2026-10-30 阅读。引用支撑 SDK／沙箱能力；模块划分、协议与数据模型均是 WorkX 的设计决策。

| 官方来源 | 本次核对结论 |
| --- | --- |
| [Agent SDK 概览](https://code.claude.com/docs/en/agent-sdk/overview) | 提供 Python／TypeScript SDK，包含 Agent loop、工具、MCP、Skills、会话和 Hooks；产品使用 API 认证，不借用个人 Claude 订阅登录。 |
| [SDK 托管](https://code.claude.com/docs/en/agent-sdk/hosting) | SDK 管理 Claude CLI 子进程，具有本地目录和会话状态；需要按有状态执行进程托管。 |
| [Python SDK](https://code.claude.com/docs/en/agent-sdk/python) | Python 包为 claude-agent-sdk；交互式 ClaudeSDKClient 支持中断。 |
| [官方 Python 仓库](https://github.com/anthropics/claude-agent-sdk-python) | Python 包包含 CLI；安装包、CLI、模板和系统依赖仍需联调锁定。 |
| [会话](https://code.claude.com/docs/en/agent-sdk/sessions) | resume 需要指定会话及可恢复的会话材料；会话 fork 不自动隔离工作目录。 |
| [工具权限](https://code.claude.com/docs/en/agent-sdk/permissions) | allowed_tools 用于自动批准，不等于只暴露这些工具；自动批准可绕过 can_use_tool。 |
| [Skills](https://code.claude.com/docs/en/agent-sdk/skills) | Skills 依赖配置来源和目录发现；需有明确的加载与发布策略。 |
| [E2B 文档](https://docs.e2b.dev/) | 提供 Linux 沙箱、命令与文件操作，普通 e2b SDK 足以托管 Runner；Code Interpreter 是额外选择。 |
| [E2B 持久化](https://docs.e2b.dev/sandbox/persistence) | 支持暂停／恢复；WorkX 仍另行保存业务记录、成果和恢复材料，并自行管理清理策略。 |

SDK 和云服务持续演进，编码前必须锁定实际验证通过的版本，不将本次文档里的协议设计误作第三方已提供的 API。

目录调研补充：统一采用 `/mnt/session/{uploads,workspace,outputs}` 与 `/mnt/knowledge`；SDK cwd 自行指定。E2B 原生卷的 beta 限制与可选 `/mnt/persist` 策略见 [文件系统规范](SANDBOX-FILESYSTEM.md)，不是所有目录都对应持久卷。
