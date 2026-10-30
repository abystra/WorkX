# MCP、Skill、Connector 与凭证架构

版本：0.4 · 2026-10-30 · 目标设计，未部署

凭证领域以 [凭证落地方案](CREDENTIAL-SOLUTION.md) 为规范入口；本文件定义术语、实体和接口责任。个人与组织使用同一 tenant 隔离规则，见 [租户模型](TENANCY-MODEL.md)。**Nango 不纳入建设**，原选型结论已被本轮审查替代，不存在默认长尾接入依赖。

## 领域对象

| 对象 | 职责与边界 |
| --- | --- |
| Skill／Plugin | 审核的指令／代码包与依赖清单。Plugin 聚合组件，不因安装就获得凭证。 |
| MCP Server | 工具协议服务；HTTP 可能无认证、静态认证或 OAuth，stdio 可能需要 env／文件。协议不替代 WorkX 授权。 |
| ConnectorDefinition | transport、auth_mode、identity_mode、usage_class、固定路由、能力 schema、适配器版本与可支持状态。 |
| Installation／RuntimeBinding | 包在特定租户／项目的安装及非敏感配置、逻辑依赖到 Connection／Credential 的明确映射。 |
| Connection | 特定租户与主体的一次外部授权及 scope、上游身份和状态；不按全局 User 共享。 |
| Vault／Credential／SecretVersion | 归属与使用策略、版本化密文、加密引用；Vault 是 WorkX 逻辑对象，不是 Anthropic 托管 API。 |
| Credential Broker | 解析依赖、原生 Adapter、刷新／轮换、票据与撤销；无面向 Agent 的原始密钥读取接口。 |
| Gateway／Credential Worker | 前者在固定路由上注入；后者仅为必须读取原值的程序提供隔离执行。两者都在 Agent E2B 之外。 |

## 组件决定

| 范围 | 本轮决定 |
| --- | --- |
| WorkX 登录 | 首版必须有真实登录与可信 Membership。可复用 Keycloak OIDC；WorkX tenant 与 IdP realm 不要求一一对应。 |
| 企业身份源／组织同步 | 后续按组织策略加入 SAML／OIDC／目录同步；个人空间不强制配置企业 IdP。 |
| 标准 MCP OAuth | 复用官方 SDK 客户端协议能力，由原生 Adapter 对接元数据发现、PKCE、resource、issuer 与客户端注册策略。 |
| 飞书／企微 | 首批原生 Adapter，分别处理应用身份、用户身份、渠道与业务工具凭证。 |
| 密钥保管 | PG SecretVersion 密文＋OpenBao Transit 包装密钥，不同时启用 KV／其他 Token 平台作为另一份原始值。 |
| Nango／其他整合平台 | 当前不引入。未来若确有覆盖或成本缺口，新增选型 ADR；不得静默恢复依赖。 |

标准 MCP OAuth 并不等于统一所有 SaaS 协议。[MCP 授权规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) 区分 HTTP 与 stdio，并要求 Token 与目标资源／受众匹配。SDK 缺少某一可选注册功能时按明确策略支持或拒绝，不临时猜测授权端点；固定客户端、CIMD、DCR 的具体支持在版本矩阵中确认。

参考 [Keycloak 协议支持](https://www.keycloak.org/securing-apps/overview)；非标准 OAuth 登录不能直接当 OIDC，国内身份源需按实际协议适配。SSO 完成后仍需外部 API consent、scope 与资源权限，不能直接导出 IdP Token 充作上游 API Token。

## 实体与约束

| 记录 | 字段与约束 |
| --- | --- |
| vaults | tenant_id、owner_type=member/tenant/service、owner_ref、status；成员 owner_ref 指本租户 Membership。 |
| credentials | tenant_id、vault_id、provider、usage_class=tool/channel/model/infrastructure、identity_mode、active_version_id、status。 |
| secret_versions | 同租户 credential_id、ciphertext、nonce/tag、wrapped_dek、transit_key_version、fingerprint、validity；物理存储按落地方案，不返回明文。 |
| connections | tenant_id、owner_ref、provider、auth_mode、external_org/user、scopes、status、credential_ref、authz_epoch、refresh_owner=native_adapter；不再包含第三方连接管理 ID。 |
| authorization_requests | task／attempt／PendingOperation、发起 Membership、tenant、requested_scopes、expiry、state、result_ref；无任务的安装授权也可单独存在。 |
| oauth_transactions | request_id、state_digest、加密 PKCE verifier/device_ref、issuer/client_ref、redirect_uri、expiry、consumed_at；单次消费。 |
| credential_leases | token_hash、tenant／subject、task／attempt／sandbox、audience、tool/resource范围、authz_epoch、fence、expiry、revoked_at。 |
| pending_operations | task_id、原 operation_id、工具与参数散列、状态、回执；恢复时不以新 ID 盲目重做旧副作用。 |
| runtime_instances | installation／binding、tenant、execution_location、非敏感装配摘要、secret_version引用、清理状态。 |

跨实体采用同租户组合引用约束；密钥引用也不允许跨个人／组织空间。secret_versions 是受限密文表，因此“业务库不存明文”与“PG 存密文”一致；不要再把“业务表仅存引用”写成所有物理密文都必须在 KV。

## 状态与交互

Connection：`unconfigured → authorizing → active`，可进入 `degraded / needs_reauth / revoked / disabled`。刷新是带互斥锁的操作，不必使连接在整个刷新窗口不可用；实际 Token 不可用或授权撤销时阻断新调用。

RuntimeBinding：`missing_config / missing_secret / needs_authorization / ready / disabled / test_failed`。无认证依赖不显示多余 OAuth 页面；非敏感配置与真实秘密分栏。列表只展示身份、scope、归属、更新时间与健康状态，不回显 Secret。

需要授权的任务按 [API 状态机](API-AND-EVENTS.md) 进入 needs_auth；授权成功只使任务具备重新调度条件，不承诺所有运行进程原地无损继续。取消、超时、成员移除与重复回调必须仲裁。

## 飞书与企业微信

飞书 CLI 默认放在服务端 Connector Worker，以明确 user／bot 身份调用。官方 [扩展接口](https://github.com/larksuite/cli/blob/main/extension/README.md) 可复用凭证源、传输和命令策略；只把任务票据传给 Agent，真实 Token 在可信区。官方 sidecar 限同机，自建 relay 只是候选 PoC，不能当作官方跨机支持。

机器人 Bot Secret、消息回调加密密钥属于 channel 类，由 Channel Worker 取得；用户文档／日历工具授权属于 tool 类。它们可共用 Vault Store 加密基础，但使用服务身份、解密策略和审计均分离。个人租户没有外部企业权限时，相应企业工具不可启用。

没有自动把外部昵称映射到 WorkX User 的流程，也没有机器人身份顶替缺少的用户 consent。绑定的租户、发送者映射、当前主体与工具 Connection 全部核验；匿名触发若被允许只能使用显式受限 service principal。

## 统一 API 责任

产品 API 提供创建／更新 Secret、查询脱敏元数据、发起授权、重授权、轮换、断开。内部 Broker 提供按已验证执行上下文解析与租约，不接受任意租户、密钥路径或上游地址；Gateway 每次核验票据和操作。

Secret 产品 API 只写不回显；可信服务通过 Transit 解密，是审计的内部能力。刷新只有一个责任方，更新 Access／Refresh Token 要 CAS；请求重试区分幂等读与有副作用写。撤销本地授权、供应商授权、产品登录和数据删除分别记录结果。

部署／联调验收以 [凭证方案](CREDENTIAL-SOLUTION.md#建设顺序与验收) 和 [审查记录](ARCHITECTURE-REVIEW.md) 为准；没有凭据导出或直接把全局环境复制进 E2B 的建设项。
