# WorkX 总体架构

版本：0.4 · 2026-10-30 · 目标设计

## 架构结论

保留原图的 React／Python／E2B／Knowledge Workers／存储分层。执行层调整为 **E2B Sandbox → WorkX Runner → Claude Agent SDK → Claude CLI／模型 API**。WorkX 管理任务和授权，Claude Harness 管理一次执行中的规划、工具循环和上下文。

首版采用模块化后端与独立 Worker 进程，保持一个仓库和统一领域模型；暂不把每个模块拆成微服务。任务执行、知识处理、渠道连接可以独立扩容。

```mermaid
flowchart TB
  UI["React + TypeScript\n任务 / 文件 / Wiki / 成果编辑 / 沙箱状态"]
  CH["飞书 / 企业微信\n各自的平台适配器"]
  API["Python 3.12+ / FastAPI\n认证 · 租户 · 组织 · 角色 · 项目 · 伙伴 · Session / Task"]
  DB[("PostgreSQL + pgvector\n业务事实 / 事件 / 授权 / 知识索引")]
  Q["Outbox → Redis Streams\n任务队列 / 知识队列 / 投递队列"]
  TW["Task Worker\n租约 / E2B Adapter / Runner Adapter"]
  CW["Channel Worker\n事件去重 / 身份映射 / 回传"]
  KW["Python Knowledge Workers\n解析 / Embedding / Rerank / Wiki 草稿 / 增量索引"]
  GW["WorkX Tool Gateway\n知识检索 / 生态工具 / 资源授权"]
  CB["Credential Broker\n连接归属 / 短期票据 / 刷新与撤销"]
  AUTH["SSO / 外部授权 / 密钥系统\nKeycloak / Nango候选 / OpenBao候选"]
  PARSE["Parser Adapter\nTika候选 + 按需OCR"]
  SEARCH["可选SearchProvider\nMeilisearch评测候选"]
  OSS[("S3 兼容对象存储\n原文件 / 成果版本 / 知识快照 / 恢复材料")]
  subgraph E2B["E2B Sandbox · 独立 Linux 执行环境"]
    RUN["Python WorkX Runner\nClaude Agent SDK + CLI 子进程\nAgent Loop / MCP / 已审核 Skills"]
    RO["/mnt/knowledge · 授权快照 · 本地只读"]
    RW["/mnt/session · uploads / workspace / outputs"]
    RUN --> RO
    RUN --> RW
  end
  MODEL["Claude 模型 API\n经受控认证与网络出口"]
  UI -->|REST / SSE| API
  CH <--> CW
  CW --> API
  API <--> DB
  API --> Q
  Q --> TW
  Q --> KW
  Q --> CW
  TW -->|E2B SDK / WorkX Runner 协议| RUN
  RUN --> MODEL
  RUN -->|受限 MCP 工具| GW
  GW --> DB
  GW --> CH
  GW --> CB
  CB --> AUTH
  KW --> PARSE
  KW -.-> SEARCH
  GW -.-> SEARCH
  KW --> DB
  KW <--> OSS
  TW <--> OSS
  API <--> OSS
```

图中箭头表示逻辑依赖，不代表沙箱可以直连数据库或渠道凭证。只有 API、受信 Worker 和 Tool Gateway 能访问相应的后端存储与外部凭证。

## 语言与模块职责

| 层 | 技术 | 负责 | 不负责 |
| --- | --- | --- | --- |
| Web | React + TypeScript | 工作台、Agent Chat、项目、文件、Wiki、Artifact Editor、SSE 投影、组织管理 | 保存供应商密钥、决定租户授权、直接访问 E2B |
| API | Python 3.12+ / FastAPI | 认证、租户成员角色、资源授权、REST、事件订阅、知识及成果接口 | 在请求处理器里运行 Agent 或解析大型文件 |
| Task Worker | Python | 调度、租约、配额、沙箱生命周期、输入准备、事件落库、产物收集 | 自己再实现一套 LLM 工具循环 |
| WorkX Runner | Python，运行在 E2B 内 | 校验执行输入、调用 Claude Agent SDK、桥接 SDK 消息、响应取消 | 作出可信的企业鉴权、读取全局凭证 |
| Claude Harness | Claude Agent SDK 及其 CLI | 单次执行的 Agent loop、工具调用、上下文与 SDK 会话 | WorkX 租户、业务任务、渠道回传和最终成果数据库 |
| Knowledge Workers | Python | 解析、分块、Embedding、Rerank、索引、Wiki 草稿维护 | 与某个临时沙箱共享可写知识目录 |
| Channel Worker | Python | 平台验签／解密适配、去重、身份映射、发送策略、回执与重试 | 用平台消息直接绕过 WorkX 资源权限 |
| Tool Gateway | Python，首版可部署在 API 服务内 | MCP 工具、权限／额度校验、外部 API 调用、操作去重和审计 | 将长期平台 Secret 下发沙箱 |
| 持久层 | PostgreSQL / pgvector / S3 / Redis | 业务状态、检索索引、文件版本、异步分发 | 让 Redis 或沙箱磁盘独占保存唯一成果 |

## 相比原图的调整

| 原图内容 | 新设计 |
| --- | --- |
| OpenCode Harness | Claude Agent SDK + WorkX Runner；不只是更换模型名。 |
| E2B SDK + OpenCode HTTP API | E2B SDK 管理沙箱；自建 Runner 控制／事件协议驱动 SDK。Claude SDK 不被假设具有 OpenCode 兼容 HTTP 服务。 |
| Sandbox 内 Headless Server | 首版不开放公网 Runner HTTP 端口，使用 E2B 命令进程 stdin/stdout 的 NDJSON；控制输入用受限控制文件传递。 |
| /knowledge RO | 改为 `/mnt/knowledge/<revision>` 本地只读副本，不能用 E2B beta 卷模拟只读。 |
| /workspace RW | 改为 `/mnt/session/workspace`；输入和交付分置 uploads／outputs；单 Session 独占。 |
| Sandbox ↔ Knowledge Workers | Worker 读写持久存储，Task Worker 选择快照放入沙箱；动态检索经过 Knowledge API／MCP。 |
| User / Auth | 扩展成租户、用户、成员、部门、角色、资源授权和外部身份映射。 |
| Event Stream | 持久事件日志 + SSE 补发；运行状态、成果状态、渠道回传状态分别维护。 |

## 四条核心链路

1. **工作台任务**：登录成员选择当前企业、项目与伙伴 → API 校验权限和额度 → 同事务写任务与 outbox → Task Worker 获取租约 → 准备快照／工作区 → E2B Runner 执行 → 流式事件落库 → 成果版本入库 → 工作台显示可审阅成果。
2. **平台机器人任务**：平台事件先校验并持久化去重 → 独立于长任务完成平台要求的确认响应 → 映射成员或显式配置的受限服务主体 → 同一任务服务 → 执行完成 → delivery outbox → Channel Worker 向原绑定和会话回传。平台响应窗口按接入方式单独实现，不等 Agent 执行完成才应答。
3. **知识处理**：上传原件 → 扫描与解析 → 分块、向量和权限元数据 → 发布知识版本 → 生成带来源的 Wiki 草稿 → 按权限审阅发布。任务固定 knowledge revision，正在执行时不偷偷换底稿。
4. **成果编辑**：Runner 输出待登记文件清单 → Task Worker 独立验证文件、大小、路径与内容类型 → 上传对象存储 → 数据库登记版本与引用 → 编辑器通过 Artifact API 创建新版本；模型成功结束不等于成果已发布。

## 首版部署与目录建议

```text
apps/web/                 React + TypeScript，后续逐页替换原型
services/api/             FastAPI，领域服务、REST、SSE、Tool Gateway
services/workers/         task / knowledge / channel 消费进程
runtime/claude-runner/    E2B 内 Python Runner，SDK Adapter 与协议
infra/e2b/               模板构建、用户权限、网络策略与验证脚本
packages/contracts/      JSON Schema、事件枚举与 TypeScript 生成类型
migrations/              数据库、RLS 策略、索引与回滚
workmates-prototype/     当前原型，迁移期间用于产品验收参考
docs/                    本目录
```

以上是建议布局，当前没有创建这些服务空壳。CLI 企业扩展可以增加一个轻量 Go wrapper 构建步骤；Tika 候选为独立 Java 解析服务，主后端仍保持 Python。首版模型 ID、区域、配额、SDK／CLI 版本均通过部署配置与锁文件确定；不在前端绑定“最新模型”别名，也不照搬原型中的多模型选项。

具体生命周期见 [执行设计](CLAUDE-E2B-RUNTIME.md)，数据关系见 [数据与租户](DATA-AND-TENANCY.md)。

目录与持久卷的具体区分见 [沙箱文件系统规范](SANDBOX-FILESYSTEM.md)。原生持久卷若启用只挂 `/mnt/persist`，默认架构仍通过 S3 物化与采集，不依赖 beta 卷。

## 凭证与知识层补充选型

MCP、Skill、Connector 与实际 Connection 分开建模；Skill 不持有长期凭证。Credential Broker 维护连接归属、刷新责任方和内部短期票据；SSO 登录不等于外部业务授权。沙箱只得到面向 Gateway 的受限票据，飞书 CLI 默认运行在受控 Connector Worker，用官方扩展接集中凭证与命令策略。详见 [凭证与 Connector](CREDENTIALS-AND-CONNECTORS.md)；按使用方式分类的注入路径与分期见 [凭证落地方案](CREDENTIAL-SOLUTION.md)。

知识链路为“Connector／上传 → S3 → Worker → Tika 等 Parser → 标准化块／版本／ACL → SearchProvider → Knowledge API → Claude”。Meilisearch 属检索候选，不是文件解析器；若选其作为主混合检索层，就不默认重复维护 pgvector 同功能索引。当前 pgvector 基线暂保留，待相同中文语料与 ACL 场景评测后定案，见 [Knowledge 选型](KNOWLEDGE-PIPELINE.md)。

## 异构认证与 Skill 运行配置

不能让 Nango 成为所有连接的强制入口。Connector Registry 显式声明 transport、auth_mode 和 execution_location：无认证 HTTP MCP 走普通 Adapter，静态 Header 走 Secret Resolver，OAuth 按能力选择 Nango／原生 Adapter，本地 stdio 和 Skill env／文件配置由 Runtime Launcher 管理。具体判定与门槛见 [Nango 评审](NANGO-ADOPTION.md)，运行装配与隔离见 [Skill Runtime](SKILL-RUNTIME-CONTRACT.md)。

Meilisearch 候选已核实可配置自动 Embedder 和语义／混合检索，下一阶段优先验证其作为主检索层；WorkX 保留文件解析与业务切块。模型、索引及 ACL 验证通过前，原 pgvector 基线作为对照／回退，不默认建设两套自动向量化管线。
