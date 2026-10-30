# Skill 与 MCP 的运行配置、环境变量和密钥注入

版本：0.1 · 2026-10-30 · WorkX 自建契约，尚未实现

## 建模原则

Skill 不必自带凭证，但确实可能依赖独立环境变量、`.env`、证书、API key、OAuth Connection 或本地工具。系统要支持这些依赖，不能一律要求“都改成 OAuth”，也不能因为包里没有密钥就认为它能直接运行。

将 **包定义、安装、运行配置、凭证绑定和每次注入实例** 分开：

| 对象 | 保存内容 |
| --- | --- |
| SkillVersion／McpServerDefinition | 审核后的程序与声明：版本、入口、参数、配置 schema、需要的逻辑 Secret、网络目标与权限。 |
| Installation | 哪个企业／项目可用，允许哪些成员和 Agent 使用。 |
| RuntimeBinding | 该安装的非敏感配置值、Connection 选择、Secret 引用以及注入目标。 |
| SecretVersion | 密钥库中的真实值和轮换记录；不放进 Skill 包或 Git。 |
| RuntimeInstance | 本次调用装配的 env／临时文件、子进程、租约和清理记录。 |

以下 schema 是 WorkX 扩展约定，不是 Claude SKILL.md 的官方字段。已有 Skill 使用 `.env.example`、README 或脚本说明时，可以辅助识别依赖，但正式运行需要人工审核并登记；不能自动执行包内 install 脚本、自动采集本机 `.env` 或把占位值当成真实凭证。

## 声明示例

```json
{
  "schema_version": "1",
  "skill_id": "sales-report",
  "version": "1.0.0",
  "execution": {
    "kind": "command",
    "location": "connector_worker",
    "argv": ["python", "report.py"],
    "working_directory": "skill_instance"
  },
  "configuration": {
    "REGION": {"type": "string", "required": true, "secret": false}
  },
  "credentials": {
    "REPORT_API_KEY": {
      "kind": "static_secret",
      "required": true,
      "inject": {"type": "env", "name": "REPORT_API_KEY"}
    },
    "CRM_CONNECTION": {
      "kind": "connection",
      "required": true,
      "inject": {"type": "gateway_handle"}
    }
  },
  "optional_files": [
    {"name": "runtime.env", "format": "dotenv", "enabled": false}
  ]
}
```

实际绑定只保存 `secret_ref` 或 `connection_ref`，名称在单个安装范围内解析；两个 Skill 即使都使用 `API_KEY`，也不能共用全局环境变量。值装配规则：平台保留配置不可覆盖 → 企业／项目授权默认值 → 安装级配置 → 允许用户填写的本轮非敏感参数。Secret 永远经有权限的 Resolver 读取，不接受模型随意指定密钥路径。

## 各类运行方式

| 类型 | 注入与执行方式 | 约束 |
| --- | --- | --- |
| 仅指令 Skill | 只发布审核指令与工具引用。 | 不创建虚假的 OAuth／Secret 依赖。 |
| 公开远程 MCP | 直接配置受审 URL，无上游凭证 Header。 | WorkX 入站授权、域名和工具范围仍有效。 |
| API key／Header MCP | 在 Gateway／远程 Adapter 中注入 Header。 | 值不写到模型可见的配置说明；协议需要 Basic、自定义 Header 时按 schema 适配。 |
| OAuth MCP | Broker 完成授权／刷新，Gateway 代理；Nango 可选。 | 不假设 SDK 会替用户打开浏览器和管理 consent。 |
| stdio MCP | Launcher 创建子进程的专用 env 与 cwd。 | 主进程不可通过全局 os.environ 修改承载并发租户；审核后使用固定程序与参数。 |
| 本地脚本依赖 env，且原样发送密钥 | 优先改为 Gateway 地址（BASE_URL）；无法改地址时，env 中只写占位符，由出口代理对 allowed_hosts 替换（P2）。 | 只适用于原样发送密钥的客户端；签名或换取 token 的情况按 C 类在沙箱外处理，见 [凭证落地方案](CREDENTIAL-SOLUTION.md#四类使用方式)。 |
| 本地脚本依赖 env，需读取原值 | 按该 RuntimeInstance 设置子进程 env。 | 不把每个 Skill 的秘密注入整个 Claude CLI／全部 Bash 子进程。 |
| 脚本强制读 `.env` | 仅在确有需要时创建独立临时工作目录中的 `.env`，运行后清理。 | 不改只读 `/mnt/skills` 包，不在项目共享目录或 `/mnt/persist` 留存。 |
| 证书／私钥／SDK JSON 文件 | SecretFile Adapter 创建临时文件，传路径给受控程序。 | 记录文件类别与用途，权限限定，不进入成果采集或恢复包。 |

[Claude SDK MCP 文档](https://code.claude.com/docs/en/agent-sdk/mcp) 提供 stdio 的 `env`、远程 HTTP 的 `headers` 配置，并说明 SDK 不代跑交互式 OAuth。它是运行配置手段，不代表自带 WorkX 的 Secret Resolver、Skill 专用环境或租户隔离。

## `.env` 与环境变量的具体规则

1. `.env` 只是配置序列化方式，不是加密存储。`.env.example` 可随审核包分发；真实 `.env` 由 Resolver 在执行时生成。
2. 使用约定的 dotenv 库／数据解析器，禁止 `source` 不可信文件或用 shell eval 读取配置。不同语言库对引号、换行、插值规则可能不同，按 Skill runtime profile 固定并测试。
3. 临时目录由 Launcher 生成，权限收紧；生成文件前防符号链接，默认仅受控执行进程可用。不要把原始密钥放在命令行参数、错误消息、Prompt、工具说明或审计正文中。
4. 使用 `subprocess` 独立 env map 和 argv 数组启动，白名单继承必要的 PATH／语言运行配置；不把服务端整套环境向下复制，也不允许 Skill 覆盖保留的身份、票据、代理与安全配置。
5. 仅注入声明且已授权的变量；缺失时报出变量名、用途和授权入口，不显示值。可选配置是否使用默认值需在 schema 中明确。
6. 写入真实值前先判断能否改用 Gateway 注入或出口占位符；多数 `.env` 中的 API Key 属于原样发送的 A 类，不需要真实值进入执行环境。静态 key 不存在真实短期签发机制时，注入它仍然暴露静态 key，不能称为“已转换为短期凭证”。优先将依赖它的程序留在可信 Connector Worker，经 Gateway 提供能力。

## 隔离边界与例外

同一个 E2B 环境里，同 UID 的代码可能读取对方的环境、临时文件或进程信息。为子进程单独设置 env、创建 0600 文件，不等于对同沙箱其他代码实现了可靠的秘密隔离。Skill 懒加载也不是进程隔离：Claude 普通 Bash 调用不会自动具有“当前 Skill 专属的 env”。

默认路径是“Skill → 受限工具 → Gateway → 可信 Worker”；无法代理、确需持有真实凭证的脚本，进入单独、短生命周期的执行环境或已证明隔离的 Worker，不与多个不互信 Skill 共用可写空间。启动前明确该类执行会使凭证进入此进程，不沿用“从不进入执行环境”的描述。

凭证型临时执行环境不进入复用池、不暂停保存含秘密的内存状态；关闭执行环境后按策略销毁，不只删除 `.env` 就宣称内存／供应商快照已清除。持久化只导出经白名单检查的结果，临时文件、env、认证缓存和秘密均排除。票据撤销先发生，文件清理是补充措施；重试需重新鉴权与装配，不复用上次密钥文件。

## 产品配置与交互流程

安装 → 检查依赖 → 填非敏感配置 → 选择已有连接／填写新 Secret → 检查用途、归属与权限 → 连接测试 → 启用。没有认证依赖的包可直接进入配置／测试，不出现多余授权页面。

状态至少包含 `missing_config`、`missing_secret`、`needs_authorization`、`ready`、`disabled`、`test_failed`。配置页显示 Secret 名称、来源、末次更新和是否可用，不回显原值；个人连接与企业连接可分别选择且受授权限制。

运行时按所需逻辑能力解析依赖，依次核验企业／成员状态、Installation、工具范围、Secret／Connection 归属和当前租约；注入、执行、审计、清理均记录 RuntimeInstance。取消、超时与进程崩溃由外部 Supervisor 清理，不能依赖 Skill 脚本主动删除文件。

## 验收

同名变量不同 Skill 不串值；缺失配置不误报 OAuth；none 模式不附加多余 Token；Header／env／文件模式分别生效；子进程不继承全局秘密；`.env` 含特殊字符不会执行代码；取消与崩溃后清理；跨租户 Secret 引用拒绝；成果和恢复包不含凭证；SDK 缺认证工具的状态不会被误判为任务已成功。
