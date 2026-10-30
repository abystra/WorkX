# ADR-0002：原生 Broker、沙箱外凭证与无 Nango 方案

日期：2026-10-30 · 修订：2

状态：架构规则已确定；SDK／平台／运行隔离待 PoC
关联：[凭证规范](../CREDENTIAL-SOLUTION.md)、[租户模型](../TENANCY-MODEL.md)、[ADR-0001](0001-claude-agent-sdk-on-e2b.md)

## 背景与本次修正

吸收 Claude 会话的使用方式分类、Gateway 注入和受控 Worker 方向。本轮审查发现旧文件同时存在 KV／Transit、多方刷新、E2B 原值注入例外、Nango 优先或长尾依赖，以及“授权后原 Attempt 无条件继续”的不同约定，现统一取代。

Managed Agents Vault 仅作产品模式参考，不能当作 Agent SDK 在 E2B 中自动具备的能力。具体修正记录见 [架构审查](../ARCHITECTURE-REVIEW.md)。

## 决定

1. 五类路由为 0 无凭证、A 原样发送、B 用户 OAuth、C 换取／签名、D 本地读取。Skill／MCP／Connector／Plugin 的依赖按路由处理，包不包含秘密。
2. 所有真实上游 Secret，包括模型 key，均不进入 Agent E2B。Gateway 注入、C 类交换／签名与 D 类读取在可信区；不再有“另建 E2B 就可注入原值”的例外。
3. Vault Store 使用 PG 版本化密文＋OpenBao Transit 包装密钥；产品读取 API 不回显原值，内部解密由服务身份授权，不同时建 KV 原值副本。
4. 自建薄 Broker／Gateway，标准 MCP OAuth 复用 SDK，飞书／企微按原生 Adapter。**Nango 不引入**，不保留默认长尾依赖。
5. 个人与组织空间共用 tenant 模型；个人连接不能跨租户借用。Vault 合并是当前租户授权交集，而非把某 User 的所有凭证汇总。
6. needs_auth 保存 PendingOperation 并结束旧 Attempt；有效授权后在同 Task 新建 Attempt、fence、票据，检查点与副作用均核对后恢复。晚到回调不复活取消任务。
7. lark-cli 默认服务端执行；官方同机 sidecar 的跨 E2B relay 只是可选自建 PoC，HMAC／时间戳不能替代操作幂等和在线授权。
8. 首选固定路由 Gateway；P2 优先评估供应商出口 Header 注入，必要时才自建 TLS 终止代理。普通 HTTPS_PROXY 不是密钥替换或强制网络隔离。

## 影响与取舍

减少外部中间件，但必须实现租户归属、密文版本、票据、原生授权、撤销和重放核对。D 类依赖只能在隔离 Worker 支持后启用；不为兼容任意脚本破坏 E2B 边界。SSO 高级功能可分期，但真实登录与 Membership 隔离在 P0。

## 未采用

| 方案 | 原因 |
| --- | --- |
| Nango 及额外的统一连接平台 | 当前范围无必要，避免双生命周期；不据此评价其所有能力或地域适用性。 |
| 在 E2B 写真实 env／`.env`／密钥文件 | 违反本产品执行边界，原值依赖转可信 Worker。 |
| 凭证只写不读意味着服务端不能解密 | 无法执行代理调用；只写不回显是产品 API 约束。 |
| 依靠 HMAC 时间戳消除所有重放 | 仍有有效时间窗口，需请求去重、operation_id、回执与授权。 |
| 托管 Vault API 直接套进 SDK 自托管 | 属不同产品与托管方式；切换需要另行决策。 |

## 验收

以 [凭证方案](../CREDENTIAL-SOLUTION.md#建设顺序与验收) 和 [API 状态机](../API-AND-EVENTS.md) 为准。尚未完成真实 OAuth、Worker 隔离、出口强制或 sidecar relay 联调，本 ADR 不代表这些能力已实现。
