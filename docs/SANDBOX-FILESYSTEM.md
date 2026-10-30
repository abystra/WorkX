# 沙箱目录、挂载与持久化规范

版本：0.2 · 调研日期：2026-10-30 · 状态：WorkX 目标约定，尚未部署验证

## 调研结论

采用 `/mnt/...` 作为 WorkX 沙箱中数据目录的统一命名方式，有 Claude 官方产品和 E2B 示例可参考。但这不是“所有 Claude 环境都必须使用 /mnt”的统一协议，也不意味着创建该路径就已挂载持久卷。

| 范围 | 官方资料确认的行为 | 对 WorkX 的意义 |
| --- | --- | --- |
| Claude Managed Agents 托管文件 | 上传资源映射到 `/mnt/session/uploads/...`，交付文件放在 `/mnt/session/outputs/`；API 的 `mount_path: /data.csv` 会被放入 uploads 目录。 | 可以参考它的输入／输出语义；这套 Files API 和路径重映射不自动适用于自托管 Agent SDK。 |
| Claude Agent SDK | 通过 `cwd` 指定执行目录，官方托管示例使用 `/work/session-a`；默认会话状态位于用户 Claude 配置目录。 | 我们自己创建目录并指定 cwd；SDK 不自动创建、挂载或同步 WorkX 的数据目录。 |
| SDK Skills | 从配置来源对应的 `.claude/skills/` 等位置发现 Skills。 | 任意 `/mnt/skills` 不会仅因名字相似就自动被 SDK 发现；必须显式适配发现来源。 |
| E2B 原生 Volumes | `volume_mounts` 的键是沙箱内自定义挂载路径，官方示例为 `/mnt/my-data`。 | 可以选用 `/mnt/persist`，不要求路径必须叫 my-data。 |
| E2B Volumes 可用性 | 官方当前标为 private beta；有只读、权限、锁和快照等限制。 | 不能把原生卷作为当前已验证、必然可用的基础依赖。 |
| E2B Cloud buckets | 可用定制模板和 FUSE 挂载对象存储，官方也展示 `/home/user/bucket`。 | `/mnt` 是我们的目录约定；原生卷、FUSE、文件复制是不同机制。 |

来源：[Claude 文件路径](https://platform.claude.com/docs/en/managed-agents/files)、[SDK 托管与 cwd](https://code.claude.com/docs/en/agent-sdk/hosting)、[SDK Skills](https://code.claude.com/docs/en/agent-sdk/skills)、[E2B 挂载卷](https://docs.e2b.dev/volumes/mount)、[E2B Volumes 概览](https://docs.e2b.dev/volumes)、[E2B Cloud buckets](https://docs.e2b.dev/storage/cloud-buckets)。

用户记忆中的 `/mnt/user-data/uploads`、`/mnt/user-data/outputs` 和 `/mnt/skills` 可能来自其他 Claude 产品环境。本轮未从所阅读的官方 SDK 文档确认它们是对外承诺的统一规范，不以第三方转载的系统提示词作为规范依据。WorkX 采用公开文档可确认的 `/mnt/session` 输入输出语义，同时保留自己的知识和持久化层。

## WorkX 目录约定 v1

以下均是 **E2B Linux 沙箱内部路径**，不是用户 Mac 的目录，也不是 S3 object key。无需在开发者电脑上创建 `/mnt` 或修改宿主机挂载配置。

```text
/mnt/
  session/                         本 Session 本地数据根，非共享租户卷
    uploads/                       本轮上传及授权输入副本，Runner 只读
    workspace/                     cwd，代码／草稿／计算过程，Runner RW
    outputs/                       待采集的最终交付文件，Runner RW
  knowledge/<revision>/            授权知识快照，本地只读副本
  skills/<bundle_revision>/        已审核 Skills 源包，本地只读
  persist/                         可选 E2B 原生持久卷，仅限本 Session，RW
/opt/workx/                        Runner 和已安装工具，只读模板内容
/run/workx/<attempt_id>/           执行输入、控制文件与临时事件
/home/agent/.claude/               本 Session SDK 会话与受控配置
/tmp/                             可丢弃的工具临时文件
```

| 路径 | 权限目标与用途 | 默认实现／持久化 |
| --- | --- | --- |
| `/mnt/session/uploads` | 仅当前主体有权读取的输入；修改前复制进 workspace。 | 受信准备流程从对象存储下载到本地文件系统并设只读；原件在 S3。 |
| `/mnt/session/workspace` | SDK cwd，运行代码、Git、构建和修改草稿。 | 本地文件系统 RW；在一致性边界保存工作区检查点。 |
| `/mnt/session/outputs` | 所有待登记成果的固定出口，与中间文件分开。 | 本地 RW；Task Worker 独立校验并上传 S3、登记 ArtifactVersion 后才发布。 |
| `/mnt/knowledge/<revision>` | 本次授权的知识快照，不能由模型覆盖。 | 本地只读副本或改用 Knowledge MCP；不使用当前 beta 原生卷承载只读知识。 |
| `/mnt/skills/<bundle_revision>` | 审核后固定版本的 Skill 文件。 | 模板或受信流程发布到本地只读目录，Adapter 配置 SDK 可发现来源并验证实际加载结果。 |
| `/mnt/persist` | 可选的会话检查点、已关闭文件和输出副本。 | 原生卷可用并验证后启用；不把活跃 Git／依赖目录／数据库／锁文件默认放在卷上。 |
| `/home/agent/.claude` | SDK 会话和审核配置；仅当前 Session。 | 留在本地文件系统；恢复包只选择性保留会话材料，排除配置中的票据与认证缓存，不整目录打包。 |

目录常量由 Runtime 配置生成，并同步到 RunSpec、SDK cwd、系统指令、工具和成果采集器。前端使用 file_id、artifact_id 与 version_id，不直接拼接沙箱绝对路径。

`/mnt/session/outputs` 在 WorkX 中不会因为与 Managed Agents 同名就自动进入 Anthropic Files API。上传、版本登记和权限检查始终由 WorkX Artifact Service 完成。

## 挂载与物化是两件事

1. **默认文件物化**：从 S3 下载授权文件至沙箱普通目录，由本地文件系统权限控制只读，完成后主动上传成果／检查点。没有独立持久卷，也不能称作 S3 已挂载。
2. **E2B 原生卷**：独立于沙箱生命周期的存储，创建沙箱时显式绑定到 `/mnt/persist`。服务端保存 tenant_id／session_id → volume_id 映射，禁止用户提交任意卷名；一个卷不用于不同 Session 的共享工作区。
3. **对象存储 FUSE**：单独的候选实现，涉及驱动、凭证、缓存和文件语义。首版不默认开启，更不能将整个企业 bucket 暴露给每个任务；如以后采用，限定授权前缀与真实只读参数并单独验收。

原生卷的 beta 约束见 [E2B 官方限制](https://docs.e2b.dev/faq/volumes-beta-limitations)：当前不支持只读挂载和卷快照，Linux 用户间的读写权限位不生效；文件锁、小文件操作和挂载生命周期也有限制。因此，不能在 beta 卷上执行 `chmod` 后就宣称知识已只读，也不能把卷快照与沙箱快照混为一谈。

只读约束仅在通过验证的本地文件系统／部署机制上成立。模板用非 root、无 sudo 的 Runner，检查本地只读数据不可改写；原生卷保持 RW 定位。若本地只读保护也不可证明，撤销知识副本下发并改走受控 MCP。目录名、SDK 权限或提示词都不能替代这些措施。

## 旧方案调整

| 旧路径 | 新路径 | 含义 |
| --- | --- | --- |
| `/workspace` | `/mnt/session/workspace` | 工作目录，SDK cwd 跟随调整。 |
| `/workspace/input` | `/mnt/session/uploads` | 授权输入独立只读。 |
| `/workspace/output` | `/mnt/session/outputs` | 最终交付出口从工作目录移出。 |
| `/knowledge/<revision>` | `/mnt/knowledge/<revision>` | 知识快照，权限语义不变。 |
| `/opt/workx` 内的 Skills 源包 | `/mnt/skills/<bundle_revision>` | 数据包与 Runner 安装目录分开；需要 SDK 发现适配。 |

当前没有已部署的沙箱或后端需要搬移；这是文档中的目标路径更新。未来已运行会话不得仅替换字符串就调用 resume，应检查原 cwd、会话材料与配置版本，必要时新建 Session，避免恢复不兼容。

## PoC 验收增补

- SDK 实际 cwd 与约定一致，能读 uploads、写 workspace 和 outputs，不能改 uploads／knowledge／skills。
- 使用 Bash、Python 和符号链接等路径访问验证权限目标，不仅验证 SDK Read/Edit。
- 原生卷资格和版本核实后再测创建、重建挂载、检查点完整性与删除；不要假设当前账户已开通 beta。
- 本地 Git、构建与活跃会话文件保持正常锁语义；复制到持久卷的检查点先冻结写入、验证散列，再登记。
- 供应商 beta 权限限制不能通过共享卷绕过租户隔离；跨 Session 不共享可写卷。
- 无卷模式下 S3 备份／恢复、成果采集仍能完整运行；浏览器看到的是 WorkX 授权文件引用。

## 凭证与暂停的统一边界

[凭证规范](CREDENTIAL-SOLUTION.md) 优先适用：所有真实上游 Secret 都不进入 Agent E2B，包括模型 key、Token、证书和员工 CLI 缓存。`.env` 若只有非敏感配置可以按 [运行契约](SKILL-RUNTIME-CONTRACT.md) 创建；包含真实 Secret 时只能在沙箱外 Credential Worker 装配，Worker 临时目录不映射进上述 `/mnt`。

票据和 relay 签名材料也是秘密，但只授予本 Attempt 的有限代理权；它们仅运行时使用，不放入成果或恢复包，暂停前撤销，恢复后重新签发。不能只删 `.env` 就声称清除了进程内存。直接 FUSE 挂载若要求在 Agent E2B 放入对象存储原始密钥，则当前方案不支持；保留受限 S3 物化／采集路径。

同用户的 personal 与 organization 必须使用不同的 tenant／Session 映射、卷与恢复包。供应商 Secret Store 的出口注入是后续 Adapter 评测，不改变本目录规范，也不意味着真实值可写入沙箱环境。
