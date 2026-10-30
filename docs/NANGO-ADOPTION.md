# Nango 引入可行性与接入边界

版本：0.1 · 2026-10-30 · 结论：有条件可引入的 OAuth Adapter，不是必选的统一执行底座

## 建设决策

**Nango 可以进入 WorkX 系统建设，但仅通过可替换 Adapter 承担适配成功的外部授权／代理。不能把全部 MCP、Skill、CLI 及环境变量管理都放到 Nango。** WorkX 自建的连接注册、主体授权、Gateway、运行配置与 Secret Resolver 仍是必需能力；即使不启用 Nango，也应能运行无认证 MCP、静态密钥连接和首批自建平台 Adapter。

这是一项文档及接口可行性审查，尚未完成真实 OAuth／MCP 联调或生产验收。本机 Docker CLI 存在但 daemon 未运行；本轮没有启动 Docker、安装中间件、申请账号或使用供应商凭证。下文把“官方能力已核实”和“WorkX 尚需验证”分开记录，不将前者写成已接入。

## 官方确认的能力与限制

| 范围 | 已确认 | 对 WorkX 的决定 |
| --- | --- | --- |
| MCP OAuth | 有目录 Provider 与 Generic MCP OAuth2；Generic 当前要求 DCR 或 CIMD。目录 Provider 还有静态客户端注册模式。 | 区分 Generic、目录与自定义 Provider，不能承诺输入任意 MCP URL 即可授权。 |
| Token | 支持已适配 OAuth 的刷新与失效处理。 | 委托后不再让自建 Broker 并发刷新相同 Refresh Token。 |
| Agent sessions | 可限定连接、工具与会话票据；默认工具范围及代理能力需显式收窄。 | 服务端指定确切连接与工具；不把管理 API key 交给业务 Agent。 |
| 免费自托管 | 官方矩阵含 Auth／Proxy，不含完整 MCP Server、工具执行、Webhook、RBAC、审计等。 | 可以评测 Auth／Proxy 子集，不能用免费版假设覆盖完整运行链路。 |
| 许可与部署 | 仓库使用 Elastic License；完整自托管有企业方案。 | 实际构建版本、许可和预算确认前，不作为生产硬依赖。 |

依据：[MCP Auth](https://nango.dev/docs/guides/auth/mcp-auth)、[刷新](https://nango.dev/docs/guides/auth/token-refreshing)、[Agent sessions](https://nango.dev/docs/guides/agent-sessions)、[自托管功能矩阵](https://nango.dev/docs/guides/platform/self-hosting/self-hosting)、[仓库与许可](https://github.com/NangoHQ/nango)。以上事实截至调研日期，具体部署以固定版本和所选方案为准。

## 认证方式分流矩阵

| 连接类型 | 是否需要外部授权交互 | WorkX 路由 | Nango 角色 |
| --- | --- | --- | --- |
| 远程 HTTP MCP，无认证 | 无；仍有租户启用、地址与工具范围审批。 | Gateway／MCP Adapter，不注入上游 Authorization。 | 不需要。 |
| 远程 HTTP MCP，静态 API key／Bearer／Basic／自定义 Header | 输入并保管凭证；通常没有 OAuth 回调。 | Secret Resolver＋HTTP Adapter；请求时注入受限凭证。 | 仅在已适配 Provider 需要统一保管／代理时选择，不自动走 Generic MCP OAuth。 |
| 远程 HTTP MCP，OAuth＋DCR／CIMD | 有；可能涉及动态注册、资源发现和用户同意。 | NangoAuthAdapter 优先评测；WorkX 维护归属与授权。 | Generic 支持方向，需验证服务互操作与所选部署方案。 |
| OAuth，固定 Client ID／Secret，无自动注册 | 有，需预先注册应用。 | 已支持的目录 Provider 或自定义 OAuth Adapter。 | 不能套用 Generic 的 DCR／CIMD 承诺；逐 Provider 验证。 |
| 本地 stdio MCP，无凭证 | 不需要 OAuth；需要审核程序与运行环境。 | Process Launcher，独立命令／参数／cwd。 | 不需要。 |
| stdio MCP，需要 env／文件／本机钥匙串 | 视实际凭证类型，可能先外部授权。 | Runtime Binding＋Secret Resolver；优先受控服务端进程。 | 可为底层 OAuth 连接提供凭证生命周期，不代替子进程启动与文件注入。 |
| Skill，需要独立 `.env` 或密钥文件 | 按声明补齐配置、连接和 Secret；不必都是 OAuth。 | Skill Runtime Binding，见 [运行契约](SKILL-RUNTIME-CONTRACT.md)。 | 仅当依赖某个已适配 OAuth Connection 时参与。 |
| 飞书 CLI 的 user／bot、设备授权与企业配置 | 按身份、应用 scope、用户授权分别完成。 | 官方 CLI 扩展＋服务端 Connector Worker。 | 对具体授权流程做 Adapter PoC，不能宣称可直接接管全部设备登录／DPoP／本机凭证。 |

`auth_mode=none` 仅表示上游不校验凭证，不意味着关闭 WorkX Gateway 入站鉴权。无认证服务也可能发送请求、读外部数据或触发操作，需要同样的工具授权与调用审计。

## WorkX 适配接口

以下是 WorkX 内部设计接口，不是对 Nango API 的逐字封装：

- `begin_authorization(context, connector, requested_scopes)`：返回交互句柄或“不需要 OAuth”；浏览器仅收到必要的短期授权入口。
- `complete_authorization(handle, verified_provider_result)`：服务端核验主体、scope、企业与状态，不能相信前端提交的 connection_id。
- `get_connection_status(context, connection_ref)`：统一 active／needs_reauth／degraded 等状态，不返回密钥。
- `invoke(context, connection_ref, operation)`：校验方法、地址、工具、参数和审批后调用具体 Adapter。
- `disconnect(context, connection_ref)`：先禁用 WorkX 调用，再处理上游撤销及失败重试。

Provider Adapter 可以是 `nango_oauth`、`native_oauth`、`static_secret` 或 `none`。WorkX Connection 记录使用哪个凭证责任方；业务模块不直接依赖 Nango 数据表、标签或 SDK 对象。

Nango 集成流程：API 创建受限授权会话 → WorkX 前端打开 Connect UI → 回调验签或服务端核验 → 写 WorkX Connection 映射 → Gateway 代理调用。后端可经 HTTP API 接入，主服务不必从 Python 改为 TypeScript；只有选择 Nango Functions 时另行评估其运行时与构建成本。

MCP Session ID、通知、流式响应、重连、取消、错误语义不能在“能代理一次 tools/call”时就算验证通过。需在已支持协议／版本上测试 initialize、tools/list、tools/call、会话 Header 与流处理，并检查与 Claude Agent SDK 的互操作。

## Agent sessions 的产品化约束

Nango 官方 Agent sessions 文档说明通用代理可绕过工具 allow／deny 范围；因此 WorkX 默认关闭 `nango_proxy`，精确限制工具，不使用全环境通配。连接由服务端从 WorkX Membership 与授权绑定解析，禁止客户端改标签或猜 connection_id 选择别人的授权。Nango 的 tenant selector 不是 WorkX 多租户权限的替代品。

管理 MCP、管理 API key 和业务执行票据隔离；默认执行链仍经 WorkX Gateway，使每次写操作能检查 authz_epoch、Attempt 租约、审批与幂等。若将 Nango session 票据直接下发沙箱，必须单独证明及时撤销与策略等价，不能仅因有 expires_at 就允许绕过 Gateway。

## 进入生产建设的验收门槛

| 检查项 | 当前证据 | 通过标准 |
| --- | --- | --- |
| API／部署能力 | 官方文档已核实；没有部署。 | 固定版本、可重复部署、备份／恢复与升级记录。 |
| 许可与功能 | 已识别免费／付费边界，未选方案。 | 所需 MCP／Webhook／审计等确实在实际许可范围内；不依赖文档里有但版本中没有的能力。 |
| OAuth 互操作 | 未使用测试账号联调。 | 至少一个目标 MCP／Provider 完成授权、调用、刷新、失效、重授权和断开。 |
| 无认证／静态认证 | 已设计旁路。 | 不经过不必要的 OAuth，且统一接受 WorkX 策略检查。 |
| 租户与主体隔离 | 仅有设计。 | 两租户／两成员的连接替换、标签篡改、回调串绑和 connection_id 猜测均拒绝。 |
| 代理策略 | 已识别通用代理扩权风险。 | 工具 allowlist 无法通过原始代理绕过；SSRF／重定向／Header 注入验证通过。 |
| 撤销与异常 | 未做实测。 | 撤销后新调用被拒，刷新并发不损坏授权，写请求超时不盲目重放。 |
| SDK 兼容 | SDK 支持 HTTP Header／stdio env 已核实。 | Claude SDK 端状态可见、完整工具调用及事件回传通过。 |

最终判定：**有条件通过技术选型评审，允许按 Adapter 进入 PoC／开发；未通过生产接入验收。** 若完整自托管成本／许可或目标协议不匹配，关闭 Nango Adapter，保留自建首批 Provider 与无认证／静态认证路径；不让它阻塞系统核心能力建设。
