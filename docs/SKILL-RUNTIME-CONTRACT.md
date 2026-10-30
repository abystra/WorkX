# Skill／MCP／Plugin 运行配置与凭证装配

版本：0.2 · 2026-10-30 · WorkX 自建契约，尚未实现

## 统一规则

本文件执行 [凭证规范](CREDENTIAL-SOLUTION.md)：真实上游 Secret 不进入 Agent E2B。需要读取原值的程序由可信 Credential Worker 承担，不再保留“单独 E2B 沙箱可注入真实密钥”的例外。`.env` 是文件格式，不是秘密存储或隔离机制；Nango 不参与运行装配。

Skill 可以依赖非敏感 env、代理票据、占位符、OAuth Connection 或原始密钥文件，不能把这些一概当作 OAuth。区分包声明、租户安装、RuntimeBinding、SecretVersion 与 RuntimeInstance；Plugin 按组件分别声明与授权，去掉 Skill 文案不等于禁用对应命令。

## 声明示例

下面是 WorkX 的附加 manifest，不是官方 SKILL.md 字段；包内只允许 schema／占位示例，不包含真实值。

```json
{
  "schema_version": "1",
  "skill_id": "sales-report",
  "version": "1.0.0",
  "execution": {
    "kind": "command",
    "location": "credential_worker",
    "argv": ["python", "report.py"],
    "working_directory": "runtime_instance"
  },
  "configuration": {
    "REGION": {"type": "string", "required": true, "secret": false}
  },
  "credentials": {
    "REPORT_API_KEY": {
      "usage": "D",
      "kind": "static_secret",
      "required": true,
      "inject": {"type": "env", "name": "REPORT_API_KEY"}
    },
    "CRM_CONNECTION": {
      "usage": "B",
      "kind": "connection",
      "required": true,
      "inject": {"type": "gateway_handle"}
    }
  },
  "files": [{"name": ".env", "format": "dotenv", "required": false}]
}
```

例中 REPORT_API_KEY 属 D 类，只有明确批准的 Worker 程序可读取；若脚本可改为 Gateway 调用则重新声明为 A 类，不再注入原值。真实安装记录只保存密钥／连接引用，归属当前 tenant 与 owner。未支持 D 类隔离执行的安装保持不可启用。

## 路由与装配矩阵

| 需求 | Agent E2B 内 | 可信区 |
| --- | --- | --- |
| 仅指令／无凭证 MCP | 审核指令、受限工具或本地计算 | Gateway 无上游认证头，仍核验任务票据 |
| Header／OAuth MCP | WorkX MCP URL＋票据 | Gateway 注入／原生 Adapter 刷新 |
| 可配置 BASE_URL 的脚本 | 非敏感地址与代理票据 | API／Model Gateway 注入；校验真实操作而非放开任意代理 |
| 必须直连但原样发送 key | 只允许已验证 EgressAdapter 的占位符，未支持时阻止执行 | 可选 P2 的出口 Header 注入；不支持签名／换 Token 的原值计算 |
| stdio MCP，无秘密 | 专用进程、固定 argv/cwd、白名单非敏感 env | 安装策略与资源授权 |
| stdio／脚本需原始 Secret | 仅远程工具接口 | Credential Worker 专用进程 env／临时文件 |
| 非敏感 `.env` | RuntimeInstance 临时目录；不可覆盖审核包 | 校验 schema／来源；不自动读取开发者电脑文件 |
| 真实密钥 `.env`／证书文件 | 禁止创建或挂载 | Credential Worker 临时目录，白名单输出、外部 Supervisor 清理 |

[Claude SDK MCP](https://code.claude.com/docs/en/agent-sdk/mcp) 支持 stdio env、HTTP headers 等配置，但不自带 WorkX 运行实例／凭证隔离；普通 Bash 调用不会因“正在使用某 Skill”自动进入专属环境。SDK 配置里只能放符合上述边界的值。

## env／文件规则

1. `.env.example` 允许非敏感示例；`.env` 按 schema 由 Launcher 装配，禁止 source／eval 不可信文件。dotenv 特殊字符、换行与插值规则在固定运行时验证。
2. 不修改只读 `/mnt/skills`，不把 Secret 写到 workspace、persist、模板或 SDK 配置目录。可信 Worker 的临时路径不是 Agent 可挂载目录。
3. 每个 RuntimeInstance 采用独立 argv、cwd、env map，绝不通过修改主进程全局 os.environ 切换并发用户。两个安装同名 API_KEY 也不得串值；平台身份／代理／票据配置不可被包或模型覆盖。
4. 只继承必要非敏感基础变量；密钥来源由服务端授权解析，不接受模型给任意 Secret 路径。日志只留变量名、引用、版本与结果，不留值、认证 Header 或临时授权材料。
5. 同 UID、同执行域内 env 和 0600 文件不是不互信代码间的强隔离。可信 Worker 也不得让不同租户／不互信组件共享可读取秘密的执行空间，需操作系统或独立执行单元证明隔离。
6. Credential Worker 不暂停保存带 Secret 的内存，不入 Agent 会话复用池；先撤销运行权限，再终止进程并清理临时材料，重试重新解析。销毁与保留承诺以实际平台能力为准，不能只删文件就声称彻底清除了内存／备份。
7. E2B 中的短期票据／占位符映射在暂停前撤销，不写 Prompt／SDK transcript／恢复包；恢复重新签发。模型 API key 同样留在 Model Gateway。

## 产品流程与状态

安装 → 展示依赖和使用方式 → 填非敏感配置 → 选择本租户可用连接／创建 Secret → 测试 → 启用。个人空间只有本人的授权管理；组织内共享连接与成员私有连接分别展示。没有认证依赖时不弹 OAuth 页面。

状态：missing_config、missing_secret、needs_authorization、ready、disabled、test_failed。缺失时显示逻辑变量名、用途与补齐入口，不显示值。取消配置不覆盖已有有效版本；测试不在未告知情况下发送真实业务写操作。

执行时检查租户、Membership／服务主体、Installation、RuntimeBinding、工具和资源范围、authz_epoch 及租约；缺少用户授权进入 needs_auth。授权后的任务重新调度及 PendingOperation 核对遵循 [API 约定](API-AND-EVENTS.md)，不绕过原主体和原租户。

## 验收

验证 none／静态／OAuth／env／文件各路径；同名变量不同安装隔离；个人／组织空间不能互借连接；不继承整套平台环境；Secret 不入 E2B；Worker 隔离、超时清理与取消；dotenv 不执行代码；输出、事件、SDK 转录与检查点不含秘密；不可代理依赖明确报不支持，不偷偷降级为真实 key 注入。
