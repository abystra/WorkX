# 架构审查与统一记录

日期：2026-10-30 · 审查范围：根目录 docs、产品 SaaS 说明、功能清单及入口文档

结合 Claude 会话的凭证分类／出口注入方案与用户本轮要求，已修正以下文档冲突。这里的“已统一”指设计及规范，不表示后端隔离、供应商授权或密码学实现已经验收。

## 决策与修正

| 原冲突或遗漏 | 统一结果 | 规范位置 |
| --- | --- | --- |
| Nango 同时是优先方案、可选长尾和非必需 | 当前不引入；无部署、Schema 字段或阶段计划依赖，旧评审仅保留不采用历史。 | 凭证方案／ADR-0002 |
| KV、Transit、仅存引用的不同物理存储说法 | PG 的受限 SecretVersion 保存密文＋wrapped DEK；Transit 管理主密钥，普通业务表仅引用。 | 凭证方案／实体文档 |
| “只写不读”被理解成可信服务也不能取用 | 产品 API 不回显；服务身份在可信区经授权解密，内部解密不可暴露给 Agent。 | 凭证方案 |
| E2B 禁止真实密钥，但 env／独立沙箱又有例外 | 所有上游真实 Secret 不入 Agent E2B；D 类原值读取转可信 Credential Worker，未支持则不可启用。 | Skill Runtime／执行设计 |
| 模型 key 在 PoC 可进入 Runner | Model Gateway 覆盖模型认证，测试与生产无例外。 | 执行设计／实施路线 |
| Channel Secret 在 Broker 外因而缺少统一保存／策略 | 共用加密基础，usage_class 和服务解密权限分离，不挪用渠道凭证为任务授权。 | 凭证实体／统一方案 |
| 用户凭证按全局 User 自动汇总 | Vault／Connection 按 tenant＋Membership／服务主体解析；个人租户和组织内成员私有连接明确区分。 | 租户模型／凭证方案 |
| needs_auth 无条件继续原 Attempt，长期持租约 | 旧 Attempt waiting_auth 终结并释放租约，保存 PendingOperation；有效回调后同 Task 新 Attempt，重新签票据与 fence。 | API 状态机 |
| 群中推授权链接可能混淆主体 | 群内仅 WorkX 登录入口；授权材料只给指定、已核验的同租户成员。 | 凭证方案／API |
| sidecar 似乎官方支持远程 E2B，时间戳可完全防重放 | 官方限同机；relay 是自建待验证扩展；HMAC 不能证明可信 CLI，另做去重／幂等与策略。 | 凭证方案 |
| HTTPS_PROXY 被当成透明密钥替换和强制出口 | 普通 CONNECT 不注入；网络层强制。先固定路由 Gateway，可选出口 Adapter 后续实测。 | 凭证方案／路线 |
| 忽略现有 E2B Secrets 导致默认自建 MITM | 补充原生 HTTPS Header 注入候选，不自动复制全部密钥；不适配时才评估 TLS 终止。 | 凭证方案 |
| Managed Agents self-hosted 与 Agent SDK＋E2B 混同 | 托管 Vault 只作参考，不继承其 API／保证。 | 凭证方案／ADR |
| SSO 后期才做，被误解为登录也可延期 | 基础登录与 Membership 在 P0，企业身份源／目录同步可后续扩展。 | SaaS／实施路线 |
| 个人用户没有正式 tenant，或按人数判个人／组织 | User 注册有唯一 personal，organization 可单人；资源均 tenant 非空，不隐式迁移或共享。 | 个人／组织租户 |
| SDK 配置目录整包备份可能包含认证缓存 | 选择性导出会话材料，排除凭证／票据／控制临时文件，暂停撤销、恢复重签。 | 目录／执行设计 |

## 范围与校验

- 逐份审查并更新凭证方案、实体、Skill 契约、目录、执行设计、数据模型、API 状态机、总体图、实施路线、ADR-0002 和入口。
- 新增个人／组织租户规范，同步 SaaS 产品基础与功能清单；此记录描述前一轮规范审查；后续空间制 SaaS 原型已实现本地多空间入口，正式隔离仍待后端建设。
- 检查相对链接／锚点、Markdown 围栏、JSON 示例和 Git whitespace；额外检索旧 Nango 依赖、原 Attempt 无条件继续、真实模型 key 注入等过时措辞。
- 前一轮审查仅修改 Markdown；本轮另交付空间制 SaaS 原型交互及行为验证，均不代表真实凭证与后端隔离已验收。

## 尚待真实实现验证

数据库 RLS 与连接池上下文、注册唯一约束／组织最后 owner、Transit seal／备份／轮换、Worker 隔离、模型代理流式兼容、SDK OAuth 注册策略、Callback 竞态、网络不可绕过、sidecar relay、EgressAdapter、上游回显控制及未知副作用恢复均需要专门 PoC。

这些是已明确的建设与验收项，不再通过追加互相矛盾的“例外”解决。规范入口：[凭证方案](CREDENTIAL-SOLUTION.md)、[个人／组织租户](TENANCY-MODEL.md)、[API 与事件](API-AND-EVENTS.md)。

## 后续空间制 SaaS 落地

账号设置与组织管理已拆开；新增本地空间切换、组织创建、邀请生命周期、资源共享范围和连接归属。部门只留成员属性，无权限继承。原型实现／验证边界以 [租户规范](TENANCY-MODEL.md) 和 [产品清单](../workmates-prototype/docs/PRODUCT-FEATURES.md) 为准，旧“尚无个人切换”描述已同步替换。

本轮空间原型验证：73 项 Node 行为回归通过，JavaScript 语法检查与 Markdown 链接／锚点／示例检查通过；另有桌面／390px 窄屏及中英浏览器走查。验证仅覆盖本地交互，不扩大为真实租户隔离、邀请邮件或凭证代理能力证明。
