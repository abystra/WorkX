# ADR-0002：凭证按使用方式分类，由自建 Broker 在沙箱外注入

日期：2026-10-30  
状态：推荐方案，P0 范围待 PoC 验证  
关联：[凭证落地方案](../CREDENTIAL-SOLUTION.md)、[凭证与 Connector 架构](../CREDENTIALS-AND-CONNECTORS.md)、[ADR-0001](0001-claude-agent-sdk-on-e2b.md)

## 背景

MCP、Skill、Connector、Plugin 各自又有无认证、静态 Key、OAuth、环境变量、`.env`、证书等认证方式，按来源逐一设计时组合过多，也没有一个开源中间件能统一接管。ADR-0001 已确定 Claude Agent SDK 运行在自托管的 E2B 中，因此无法直接使用 Claude Managed Agents 的 Vault；而官方文档也说明，自托管沙箱暂不支持环境变量凭证的出口替换。

## 决定

1. 凭证按运行时的使用方式分为 0（无凭证）、A（请求头令牌）、B（用户委托 OAuth）、C（换取或签名）、D（必须读取原值）五类，每类对应固定的处理路径；Plugin 的凭证需求等于其组件 manifest 的并集。
2. 真实凭证不进入 E2B。沙箱只持有任务票据和占位符；A／B 类由 Gateway 反向代理注入，C 类在 Broker 或 sidecar 中交换，D 类转到受控 Worker。
3. 参照 Claude Managed Agents 的 Vault 模型自建 Credential Broker：按主体组织 Vault，凭证以目标地址或变量名为键，只写不回显，运行中可轮换和吊销。
4. 远程 MCP 的 OAuth 客户端按 MCP 规范自行实现（CIMD 优先、DCR 兜底、PKCE、校验 `iss`）；Nango 只作为长尾 SaaS 的可选 Adapter。
5. 飞书 CLI 默认在受控 Connector Worker 运行；需要在沙箱内运行时，使用官方 `authsidecar` 模式，并通过沙箱内的回环 relay 转发到远程飞书 Gateway。
6. 执行中缺少个人授权时，任务进入 `needs_auth` 挂起，授权完成后自动恢复。

## 影响与取舍

- 需要自建 Broker、Gateway 和票据校验；换来的是租户、成员、伙伴、任务维度的授权完全由 WorkX 控制。
- Gateway 反向代理不需要 TLS 中间人，作为首选；出口占位符替换需要 TLS 终止和沙箱内置 CA，放到 P2。
- 出口替换只适用于原样发送密钥的客户端；需要签名或换取 token 的客户端必须走 C 类。
- lark-cli sidecar 官方只支持同机部署，WorkX 需要额外维护一个沙箱内 relay，其签名 key 按任务签发。
- 新增 `needs_auth` 任务状态，影响任务状态机、事件和渠道回传。

## 没有采用的方案

| 方案 | 原因 |
| --- | --- |
| 把凭证写入 E2B 环境变量或 `.env` | 沙箱内任意代码都可读取，与提示注入风险叠加 |
| Nango 作为统一入口 | 不覆盖无认证、静态 Key、stdio、Skill 环境变量；完整功能需要企业许可 |
| Arcade、Composio 等托管工具授权服务 | 主要为海外 SaaS，自托管需企业版，不满足数据驻留要求 |
| 改用 Claude Managed Agents 托管运行 | 与 ADR-0001 的自托管 E2B 决定冲突；如改变托管方式需新增 ADR |

## 待 PoC 确认

SDK 的 MCP 地址改写与票据 Header；E2B 出网 allowlist 与 `HTTPS_PROXY` 的覆盖面；出口代理 TLS 终止的兼容性；lark-cli sidecar relay；一个支持 CIMD 的远程 MCP 全流程。详见 [凭证落地方案](../CREDENTIAL-SOLUTION.md#待-poc-验证)。
