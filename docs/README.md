# WorkX 架构设计文档

版本：0.7 · 2026-10-30 · 状态：空间制 SaaS 原型已补齐，真实运行与隔离待建设

目标：React + TypeScript → Python FastAPI → E2B → WorkX Runner + Claude Agent SDK。服务个人和组织，统一 tenant 隔离，保留独立知识处理与成果存储。当前 JavaScript 原型已有个人／组织切换、独立设置、创建组织、演示邀请、数据／连接归属；尚未接通真实凭证、OAuth、租户后端或沙箱。

## 规范入口与阅读顺序

| 文档 | 负责的规则 |
| --- | --- |
| [总体架构](ARCHITECTURE.md) | 分层、模块、语言、执行与生态链路 |
| [个人／组织租户](TENANCY-MODEL.md) | personal／organization、成员、切换、资源与生命周期 |
| [凭证落地方案](CREDENTIAL-SOLUTION.md) | 凭证分类、PG 密文＋Transit、Gateway、授权恢复与阶段范围 |
| [凭证实体与协议](CREDENTIALS-AND-CONNECTORS.md) | Vault／Connection／Lease／授权请求、身份和服务边界 |
| [Skill／MCP 运行契约](SKILL-RUNTIME-CONTRACT.md) | env／`.env`／原值依赖的装配、Worker 隔离与清理 |
| [API 与事件](API-AND-EVENTS.md) | 任务、needs_auth、新 Attempt、回调及投递状态机 |
| [Claude 与 E2B](CLAUDE-E2B-RUNTIME.md) | SDK Adapter、沙箱、模型出口、取消与恢复 |
| [沙箱目录](SANDBOX-FILESYSTEM.md) | `/mnt`、本地副本、持久卷与权限 |
| [数据与租户](DATA-AND-TENANCY.md) | 实体、数据库约束、索引、文件版本与隔离 |
| [Knowledge](KNOWLEDGE-PIPELINE.md) | Tika／OCR、切块、Meilisearch Embedding 与检索评测 |
| [实施路线](IMPLEMENTATION-PLAN.md) | 分阶段交付与真实验收门槛 |
| [审查记录](ARCHITECTURE-REVIEW.md) | 本轮冲突、修正、风险与检查结果 |
| [ADR-0001](adr/0001-claude-agent-sdk-on-e2b.md) | E2B＋Claude Harness 方向 |
| [ADR-0002](adr/0002-credential-broker-and-egress-injection.md) | 原生 Broker、沙箱外密钥、不引入额外连接平台 |

规范发生重复时以负责该领域的入口为准；冲突必须修改原段落，不能仅追加一个相反的说明。

## 统一基线

- 注册用户拥有唯一 personal 租户，可另外加入 organization。个人不是 null tenant，也不是真实企业法人；资源、凭证、检索、用量和后台任务均固定归属。
- User 是全局身份，Membership 和角色属于空间。部门只作可选组织属性，首版不做权限继承。真实登录在 P0，企业 SSO 可分期。
- 凭证 0/A/B/C/D 五类；自建薄 Broker＋Gateway，原生 OAuth／国内平台 Adapter。**Nango 不引入**，历史评审不作为交付计划。
- PG 保存版本化密文，OpenBao Transit 管理包装密钥；产品 API 不回显原值，可信服务授权解密。原值不进入 Agent E2B；D 类程序只在隔离 Credential Worker。
- 模型也经 Gateway。沙箱只有短期票据／必要的临时签名材料或占位符；暂停前撤销，恢复重新签发，检查点不得打包认证缓存。
- needs_auth 释放运行租约；授权有效后同 Task 创建新 Attempt，重新验证主体、fence 和副作用，不无条件继续旧进程。
- PostgreSQL／S3 保存事实与文件；Redis Streams＋outbox 分发。知识候选 Tika＋Meilisearch 自动 Embedding／混合检索，与 pgvector 对照，不默认双向量化。

## 已核对的官方依据

| 来源 | 仅用于支撑的范围 |
| --- | --- |
| [Claude SDK](https://code.claude.com/docs/en/agent-sdk/overview)、[托管](https://code.claude.com/docs/en/agent-sdk/hosting) | Harness 与有状态执行模型 |
| [SDK 安全部署](https://code.claude.com/docs/en/agent-sdk/secure-deployment) | 代理／自定义工具模式，不等于 WorkX 已验证隔离 |
| [Managed Agents Vault](https://platform.claude.com/docs/en/managed-agents/vaults) | 产品参考，不是 E2B 自建 SDK 的现成功能 |
| [E2B Secrets](https://docs.e2b.dev/secrets)、[注入](https://docs.e2b.dev/secrets/inject) | 后续出口 Adapter 候选，非首版强依赖 |
| [OpenBao Transit](https://openbao.org/docs/secrets/transit/) | 密文在应用库、加密密钥在 Transit 的分工 |
| [Clerk 空间模型](https://clerk.com/docs/guides/organizations/configure) | 个人和组织并存是可选建模方式，WorkX 的统一 tenant 是自身决定 |

旧 [Nango 评审](NANGO-ADOPTION.md) 仅保留“不采用”的历史记录。SDK、供应商能力与许可证随版本变化，编码前锁版本并做 PoC；当前方案不是生产能力证明。

## 当前原型与产品要求

[原型运行说明](../workmates-prototype/README.md)、[产品功能清单](../workmates-prototype/docs/PRODUCT-FEATURES.md)、[SaaS 产品基础](../workmates-prototype/docs/SAAS-FOUNDATION.md)、[生态调研](../workmates-prototype/docs/ECOSYSTEM-INTEGRATION-RESEARCH.md) 继续描述现有页面和验收范围。个人空间、真实凭证与后端隔离是目标要求，不以本轮文档调整视为 UI 已实现。
