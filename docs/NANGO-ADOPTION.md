# Nango 选型历史：当前不引入

更新：2026-10-30 · 状态：不采用，原“有条件引入／长尾可选”结论已撤销

根据当前产品范围和用户决定，WorkX **不引入 Nango**。它不出现在依赖、部署、凭证责任方、Connection 字段或 P0–P2 默认交付清单中。保留本文件仅用于旧链接追溯，不作为实施规范。

此前调研了 [Nango MCP Auth](https://nango.dev/docs/guides/auth/mcp-auth) 与 [自托管模式](https://nango.dev/docs/guides/platform/self-hosting/self-hosting)。不采用并非声称它没有静态认证或代理能力，而是当前首批需求可以由 WorkX 原生 OAuth／平台 Adapter、Gateway、Credential Worker 和统一 Vault Store 覆盖，无须再引入一套连接生命周期与部署许可依赖。

原评审中的“优先接 Nango”“免费 Auth／Proxy 子集”“长尾可选 Provider”均不再是计划。如未来需求证明需要整合平台，应重新评审并建立 ADR，不能以本历史文件恢复依赖。

当前规则：[凭证规范](CREDENTIAL-SOLUTION.md)、[凭证实体](CREDENTIALS-AND-CONNECTORS.md)、[运行契约](SKILL-RUNTIME-CONTRACT.md)、[ADR-0002](adr/0002-credential-broker-and-egress-injection.md)。
