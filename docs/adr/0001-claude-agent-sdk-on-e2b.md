# ADR-0001：在 E2B 中使用 Claude Agent SDK 作为 Harness

日期：2026-10-30  
状态：E2B + Claude 方向已由用户确定；实现细节按 PoC 验证  
关联：[总体架构](../ARCHITECTURE.md)、[执行设计](../CLAUDE-E2B-RUNTIME.md)

## 背景

用户给出的原始架构是 React + TypeScript 前端、Python FastAPI 后端、E2B MicroVM 内 OpenCode Harness，以及独立 Python Knowledge Workers 和持久存储。本轮要求保留 E2B，执行内核改用 Claude，并纳入 WorkX 已确定的企业 SaaS 和多生态机器人方向。

当前仓库只有原型，尚无 OpenCode 服务或真实 E2B 适配器需要迁移，因此本次属于目标架构调整，不存在已完成的运行时热替换。

## 决定

1. “Claude Harness”定义为 Claude Agent SDK 驱动的运行时，使用官方 SDK 的 Agent loop，不在 WorkX 再写一套通用模型工具循环。
2. SDK 与 CLI 运行在 E2B 内，由 Python WorkX Runner 封装。服务端 Task Worker 管理沙箱、租约、状态和成果。
3. 用 WorkX Runner NDJSON 与控制协议替代图中的 OpenCode HTTP API；不假设存在 Claude 的等价 Headless HTTP Server。
4. 保留 Python 控制面与知识处理，React + TypeScript 作为正式前端方向。持久化与权限在沙箱外。
5. 保留 WorkX 自有的 Session、Task、Attempt 和 Delivery；通过 Adapter 映射 SDK 会话，而非把 SDK session_id 暴露为业务主键。

依据：[Agent SDK 概览](https://code.claude.com/docs/en/agent-sdk/overview)、[托管方式](https://code.claude.com/docs/en/agent-sdk/hosting)、[E2B 文档](https://docs.e2b.dev/)。SDK 能力与 WorkX 的部署决策分别记录；不将方案等同于官方现成集成产品。

## 影响与取舍

- 可以复用 Claude 工具执行和上下文能力；需要维护 SDK／CLI／模板版本兼容，不再追求 OpenCode 协议兼容。
- 执行进程有状态，必须处理工作区、会话材料、暂停、恢复、取消和超时。
- E2B 的计算隔离、SDK 的工具权限和 WorkX 的租户／资源鉴权是三种不同机制，不能相互替代。
- WorkX 获得统一业务事件和成果模型，也承担 Runner Adapter、事件重放、外部副作用核对与版本迁移成本。
- Claude 模型配置、企业授权和供应商认证需独立维护；企业机器人凭证经 Gateway 使用，不直接交给模型。

## 本轮没有采用的方案

| 方案 | 原因 |
| --- | --- |
| 仅更换模型 API，保留 OpenCode Harness | 不满足用户指定的内核替换方向。 |
| FastAPI 主进程直接运行 SDK | 会把执行文件、shell 和长会话混入共享控制面。 |
| 自写 Agent loop + Anthropic Client SDK | 与选择 Claude Harness 的目标重复，增加工具循环维护。 |
| 直接采用供应商托管 Harness | 当前选择自行在 E2B 内运行 SDK，便于明确工作区与业务控制；以后若改变托管方式需新增 ADR。 |

## 待 PoC 确认

SDK／CLI 版本、E2B 模板用户权限和网络策略、控制文件延迟、模型出口代理、跨环境会话恢复、供应商区域与配额、成本。详见 [实施路线](../IMPLEMENTATION-PLAN.md)。
