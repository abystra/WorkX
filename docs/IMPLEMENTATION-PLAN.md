# 实施路线与验收

版本：0.6 · 2026-10-30 · 目标计划，尚未接入真实后端

本轮已补齐空间制 SaaS 的本地原型交互；不把前端行为测试当作凭证、租户或沙箱的生产验收。权威规则：[凭证规范](CREDENTIAL-SOLUTION.md)、[个人／组织租户](TENANCY-MODEL.md)、[API 状态机](API-AND-EVENTS.md)。不引入 Nango，也不以企业 SSO 的延期替代首版真实登录。

## 阶段 0：运行边界 PoC

- 固定 SDK／CLI／E2B SDK／模板版本；验证 Python Runner、NDJSON、控制文件、事件、取消和成果采集。
- Model Gateway 为 Runner 注入代理票据，真实模型 API key 不进 E2B；测试流式协议、工具消息和预算。
- 验证 `/mnt` 本地只读与输出白名单、无凭据检查点、SDK 会话恢复。原生卷不承担只读保护，恢复前重签票据。
- Gateway 强制出口，测试忽略 HTTPS_PROXY 的客户端也不能直连任意上游；普通代理不能被误认成 TLS 密钥注入。

退出条件：形成版本矩阵、边界验证记录与已知限制；不可证明隔离的能力不启用。测试仅使用专用账号和最小授权。

## 阶段 1：P0 控制面与基础凭证

实现 User、personal／organization Tenant、Membership、Invitation、可选部门属性、预设角色、资源授权、登录与注册幂等。个人仅本人 owner；组织可邀请多成员，单成员组织仍可扩展。个人设置与组织管理分开，部门不做权限继承。权限在 API／Worker／Gateway／存储投影中一致生效。

实现 PG 密文＋Transit、0/A 路由、任务票据、authz_epoch、Model Gateway、基础 Credential Worker 隔离框架。只有通过受控 Worker 验证的 D 类工具可启用，其余明确不支持，不降级为向 E2B 注入原值。

验收：两租户同名资源隔离；同一 User 在个人和两个组织间切换不串 Cookie／草稿／事件；重复注册只有一个 personal；个人不能邀请第二成员；解密与 Channel／Tool／Model 服务分权；产品 API 无凭据读回；Ticket audience／tenant／fence／epoch／过期校验有效。

## 阶段 2：任务执行与成果闭环

实现 Task／Attempt／PendingOperation／Outbox／TaskEvent／ArtifactVersion、Task Worker、SDK Adapter 和 SSE。逐页迁移 React，保持英文默认／中文切换。资源、索引、用量和账单以固定 tenant 为归属，不受前台切换影响。

验收：幂等提交、事件补发、取消竞态、Worker 故障接管、旧 fence 无效、成果采集失败、未知副作用核对。SDK 成功不等于成果登记成功；恢复不重复外发或生成重复产物。个人任务不能引用组织 Connection，反之亦然。

## 阶段 3：P1 原生授权、国内平台与 CLI

标准 MCP OAuth 复用 SDK，按支持矩阵处理固定客户端／CIMD／DCR、PKCE／issuer／resource 与发现地址安全；不是自写全平台授权框架。首批飞书／企业微信分别实现 user、app、channel 与业务 API Adapter。

实现 needs_auth：缺依赖落授权请求与 PendingOperation，结束 waiting_auth Attempt 并释放租约；有效回调后同 Task 的新 Attempt 继续。取消、超时、主体失效及重复回调可仲裁。授权入口必须绑定请求主体，群内仅发登录入口。

飞书 CLI 默认在 Connector Worker 通过官方扩展执行。验收用户／应用身份、刷新 CAS、SecretVersion 切换、权限与命令策略；不复制员工本地缓存。消息接收、任务结果与投递分离，回传失败只重试已有成果。

## 阶段 4：知识与编辑

按 [Knowledge 选型](KNOWLEDGE-PIPELINE.md) 验证 Tika／OCR、结构化块与可靠引用。优先测试 Meilisearch 自动 Embedding＋混合检索，与 pgvector 基线比较后选一个主 Provider；不同时重复向量化。Meilisearch 调用模型优先经过受控 Embedding Gateway，秘密不随输入内容送模型。

验收中文扫描件、Office 表格与格式失败、索引任务完成、ACL 召回前过滤、权限撤销与缓存失效、跨空间同名文档、增量版本、编辑冲突和成果引用。数据迁移不自动迁移 Connection／Secret／运行任务。

## 阶段 5：P2 治理与可选出口适配

增加企业 SSO、目录同步、审计导出、保留期、订阅／席位／配额运营、更多受控 D 类能力。个人无需企业 IdP；组织强制 SSO 的策略在访问组织时生效。

仅在业务需要时评估 E2B 原生 Header 注入；不满足约束再考虑自建 TLS 终止代理。lark-cli 本机 relay 到远程 Gateway 是另一项独立 PoC。固定版本确认覆盖、区域、证书、撤销与回显风险，不把供应商功能名称当作已经实现。当前计划不包含额外连接授权平台。

## 核心故障与生命周期矩阵

| 情境 | 验收结果 |
| --- | --- |
| 浏览器断线／切空间 | 原任务保持原租户，授权事件按当前订阅核验，不新建执行 |
| Worker 重复消费／旧进程恢复 | 租约、唯一键、fencing 阻止重复状态提交与新工具副作用 |
| 用户在授权期间取消／离职 | 请求作废、票据撤销；晚到回调不恢复任务 |
| 授权完成但检查点丢失 | 明确需重新开始或核对，不能承诺无损继续 |
| Secret 轮换遇到在途写请求 | 新调用用新版本，在途请求核对回执，不盲目重发 |
| Transit／PG／模型出口故障 | 连接 degraded 或明确失败，不能用缓存无限绕过撤销／授权 |
| E2B 被销毁 | 业务事实仍在，按合法材料恢复；新 Attempt／票据，不复用旧权限 |
| 个人加入组织 | 个人资源与 Vault 保持独立，无隐式复制 |
| 移出组织或删除账号 | 组织／个人生命周期分别处理，最后 owner 不产生孤儿组织 |
| 代理收到重放／任意 URL | 在线策略、请求去重、operation_id、路由和网络限制共同拒绝 |

上线前用试点数据确定性能、预算、保留期、备份恢复和告警目标。尚未进行本表所列的真实平台联调；仅文档一致性检查不能代替这些测试。

当前已交付的本地交互包括空间切换、创建组织、演示邀请、资源共享范围与连接归属登记；真实身份验证、邀请邮件与一次性凭据、数据库隔离、工具授权、跨账号同步仍按上述阶段建设，不用本地演示替代。
