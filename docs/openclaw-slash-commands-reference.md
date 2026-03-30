# OpenClaw 斜杠命令与 CLI 参考

> 整理自官方文档 [Slash commands](https://docs.openclaw.ai/tools/slash-commands) 与 [CLI](https://docs.openclaw.ai/cli)。OpenClaw 版本更新时请以线上文档为准。

---

## 0. 在哪里用、整体怎么用

### 0.1 三类入口（不要混）

| 入口 | 在哪里用 | 怎么用（一句话） |
|------|----------|------------------|
| **聊天斜杠 `/...`** | 已接入 OpenClaw 的 **即时通讯**（如 Telegram、Discord、WhatsApp Web、Slack、部分 WebChat 等）里，和 **机器人对话的输入框** | **单独发一条消息**，内容以 `/` 开头（或 `! ` 跑主机命令）；由本机 **Gateway** 解析并回复。**Gateway 必须已启动**且该频道已在配置里接好。 |
| **`openclaw.json`（含 `commands`）** | **跑 Gateway 的那台电脑** 上的主配置文件 | 用编辑器或 `openclaw config` 修改 **磁盘上的配置**；保存后通常要 **重启 Gateway**（或 `openclaw gateway restart` / 系统服务重启）才会完全按新配置生效。 |
| **`openclaw` CLI** | 同一台机器上的 **终端**（PowerShell、bash 等） | 输入 `openclaw ...`，**不要**加前导 `/`。用于装插件、起网关、查状态、改配置键等。 |

### 0.2 聊天里具体怎么发

1. 打开已与 Bot 连上的 **私聊或群**（是否允许命令取决于白名单、配对、`commands.allowFrom` 等）。
2. 在输入框输入例如：`/help` 或 `/status`。
3. **发送一条只包含该命令的消息**（多数命令要求如此；少数如 `/status` 可嵌在句子里作为「行内快捷」，见第 1.2 节）。
4. 等待 Bot 返回系统回复（不是模型长文时，可能是即时命令结果）。

### 0.3 和本仓库的关系

本文件是 **OpenClaw 通用说明**，放在 `openclaw-agent-dashboard` 仓库里方便一并查阅；**Dashboard 插件不负责定义这些斜杠命令**，它们由 OpenClaw **Gateway** 实现。

---

## 1. 基本概念

| 概念 | 说明 |
|------|------|
| 谁处理 | 聊天里的 `/...` 由 **Gateway** 处理。 |
| 消息格式 | 多数命令需 **单独一条消息**，且以 `/` 开头。 |
| 主机 Shell | 使用 **`! `**（每消息一个命令）；**`/bash `** 是别名。需 `commands.bash: true` 且满足 `tools.elevated` 白名单。 |
| 可选冒号 | 命令与参数之间可写 **`:`**，例如 `/think: high`、`/send: on`。 |
| 未授权行为 | 未授权用户：纯命令消息被 **静默忽略**；普通消息里的 `/` 当 **普通文本**。 |
| 完整用量 | 各模型商用量明细可用终端：`openclaw status --usage`。 |

### 1.1 指令（Directives）vs 普通命令

| 类型 | 包含 | 行为摘要 |
|------|------|----------|
| **指令** | `/think`、`/fast`、`/verbose`、`/reasoning`、`/elevated`、`/exec`、`/model`、`/queue` | 进入模型前会从消息里 **剥离**。若整条消息 **只有指令**，会 **写入会话** 并回复确认；若混在正常句子中，多作为 **行内提示**，**不持久**改会话。 |
| **命令** | 其余 `/...` | 见下文表格。部分支持 **行内快捷**（见 1.2）。 |

### 1.2 行内快捷（仅授权发送者）

嵌入普通消息时：先执行对应逻辑，**剥掉**后再把剩余文字交给模型。

| 命令 | 作用 |
|------|------|
| `/help` | 显示帮助 |
| `/commands` | 显示命令列表 |
| `/status` | 当前状态 |
| `/whoami` | 发送者 ID（别名 `/id`） |

### 1.3 技能（Skills）相关

| 说明 |
|------|
| 用户可触发的 skill 会注册为斜杠命令；名称规整为 `a-z0-9_`，最长 32 字符，重名会加 `_2` 等后缀。 |
| **`/skill [input]`** 可按名称执行技能（当原生命令数量受限时很有用）。 |
| 默认技能命令会像普通请求一样转发给模型；若 skill 声明 **`command-dispatch: tool`**，则 **直连工具**、不经过模型。 |

---

## 2. 配置项 `commands`（`openclaw.json`）

这一节回答三件事：**文件在哪**、**怎么改**、**表里每一项控制什么、改完怎么用**。

### 2.1 `openclaw.json` 是什么、在哪里

- 它是 OpenClaw 的 **主配置文件**（JSON/JSON5 视你安装版本而定），决定 Gateway、频道、模型、插件、命令开关等。
- **默认路径**（未改环境变量时）：
  - Linux / macOS：`~/.openclaw/openclaw.json`
  - Windows：`%USERPROFILE%\.openclaw\openclaw.json`
- 若设置了环境变量 **`OPENCLAW_STATE_DIR`**，则配置根目录在该目录下（常见为 `$OPENCLAW_STATE_DIR/openclaw.json`，具体以 `openclaw config file` 输出为准）。
- 开发隔离配置可用 **`openclaw --dev`**（状态目录变为 `~/.openclaw-dev` 等），此时改的是 **dev** 用的那份配置，不是默认 `~/.openclaw` 那份。

### 2.2 怎么编辑这个文件（三种常见方式）

| 方式 | 在哪里操作 | 适合场景 |
|------|------------|----------|
| **文本编辑器** | 用 VS Code、vim 等直接打开上节路径下的 `openclaw.json` | 一次改多块配置、从文档复制整段 JSON |
| **`openclaw config`** | 终端执行，例如 `openclaw config get gateway.port`、`openclaw config set ...` | 改单个路径、脚本自动化、避免手写错逗号 |
| **`openclaw configure` / Control UI** | 终端交互向导或浏览器里的控制界面 | 初次安装、改频道登录、不熟悉 JSON 时 |

查看当前实际使用的配置文件路径：

```bash
openclaw config file
```

### 2.3 `commands` 写在哪、长什么样

在 `openclaw.json` **根级别**增加（或合并进已有）一个 **`commands`** 对象即可，与 `gateway`、`channels` 等并列。官方示例（可按需删减）：

```json5
{
  commands: {
    native: "auto",
    nativeSkills: "auto",
    text: true,
    bash: false,
    bashForegroundMs: 2000,
    config: false,
    mcp: false,
    plugins: false,
    debug: false,
    restart: false,
    allowFrom: {
      "*": ["user1"],
      discord: ["user:123"],
    },
    useAccessGroups: true,
  },
}
```

- 若你的文件是 **严格 JSON**，请把键名都加双引号，且不要尾逗号。
- 改完后：**保存文件**，并 **重启 Gateway**（例如 `openclaw gateway restart` 或重启系统服务），避免旧进程仍用旧配置。

### 2.4 各项含义：在哪里生效 + 怎么用

下面表格里 **「在哪里生效」** 指：保存并重启 Gateway 后，**哪些聊天能力**会受影响；**「怎么用」** 指：你或用户在日常里 **如何触发**。

| 配置键 | 默认值 | 作用 | 在哪里生效 | 怎么用 |
|--------|--------|------|------------|--------|
| `text` | `true` | 是否在聊天正文里解析 **`/...` 文本命令** | 所有已连接、且会经过 Gateway 文本解析的频道 | `true`：用户在对话里发 `/help` 等；`false`：一般不再把 `/` 当命令解析（无原生命令的表面上，文档说明仍可能有例外，以官方为准） |
| `native` | `"auto"` | 是否在 **Discord / Telegram** 等上注册 **平台自带** 的 Slash 命令菜单 | Discord、Telegram 等支持原生命令的平台 | `"auto"`：通常 Discord/Telegram 开启；Slack 常需自己在应用后台建命令；也可 per-channel 用 `channels.discord.commands.native` 等覆盖 |
| `nativeSkills` | `"auto"` | 是否把 **技能** 也注册成平台 Slash | 同上 | 开启后，用户在客户端命令列表里能看到技能命令；技能多时在 Slack 往往要逐个登记 |
| `bash` | `false` | 是否允许 **`! `** 与 **`/bash `** 在 **Gateway 所在机器** 上跑 shell | 聊天里发命令的那条会话（执行发生在 Gateway 主机） | 改为 `true` 且配置好 **`tools.elevated`** 白名单后，用户在授权对话里发 `! ls` 或 `/bash ls`（高风险，仅信得过环境） |
| `bashForegroundMs` | `2000` | 上述 shell **前台等待** 多久后转后台（毫秒） | 与 `bash` 同时生效 | 调大：短命令更易在同一轮回复里看到输出；`0`：立即后台 |
| `config` | `false` | 是否允许聊天里的 **`/config`** 读写磁盘上的 `openclaw.json` | 授权用户在与 Bot 的对话中 | 改为 `true` 后，**owner** 在聊天发 `/config show` 等（极敏感，仅私人环境） |
| `mcp` | `false` | 是否允许 **`/mcp`** 改配置里的 **`mcp.servers`** | 授权用户的聊天 | 改为 `true` 后，owner 发 `/mcp show`、`/mcp set ...` |
| `plugins` | `false` | 是否允许 **`/plugins`** 做插件发现、安装、启停等 | 授权用户的聊天 | 改为 `true` 后使用 `/plugins list` 等；写操作后常需重启 Gateway |
| `debug` | `false` | 是否允许 **`/debug`** 做 **仅内存** 的运行时覆盖 | 当前 Gateway 进程 | 改为 `true` 后发 `/debug set ...`；不写盘，重启即丢 |
| `restart` | （默认允许 `/restart`） | 是否允许聊天 **`/restart`** | 当前 Gateway / 服务 | 设为 `false`：禁止通过聊天重启（防误触或群控环境） |
| `allowFrom` | 不设置 | **可选** 的按提供商白名单：谁可以用命令/指令 | 所有频道上的命令与指令解析 | 一旦设置：**只认这张表**，频道白名单/配对等不再参与命令授权。`"*"` 表示全局默认键 |
| `useAccessGroups` | `true` | 未设置 `allowFrom` 时，是否用 **访问组 / 频道白名单** 等限制命令 | 同上 | `true`（默认）：与 pairing、allowlist 等一致；`false`：需结合官方文档理解放宽范围（慎用） |

**读表技巧**：前 6 行（`text` / `native` / `nativeSkills` / `bash` / `bashForegroundMs`）决定 **「用户能不能、以哪种方式在聊天里敲命令」**；`config` / `mcp` / `plugins` / `debug` 是 **高危能力开关**；`allowFrom` / `useAccessGroups` 决定 **「谁有资格用」**。

---

## 3. 聊天斜杠命令总表（文本 + 原生，启用时）

### 3.1 在哪里用、怎么用

| 项目 | 说明 |
|------|------|
| **在哪里** | 任意已通过 OpenClaw 接入的 **聊天渠道**（与 Bot 的私聊或允许的群/频道）。部分命令仅 **Discord** 等特定平台有意义（表中已标注）。 |
| **怎么用** | 对 Bot **发送消息**：多数为 **一整条消息只写命令**（可带参数），例如 `/model list`。少数命令支持夹在普通句子里的 **行内快捷**（见第 1.2 节）。 |
| **前提** | Gateway 在线；你在该对话中 **已被授权**（否则命令会被忽略或当普通文本）。 |

### 3.2 命令与作用一览

| 命令 | 作用 |
|------|------|
| `/help` | 帮助 |
| `/commands` | 列出可用命令 |
| `/tools [compact\|verbose]` | 当前会话代理 **实际可用** 的工具（运行时视图，非静态配置目录）；`verbose` 含简短描述 |
| `/skill [input]` | 按名称执行技能 |
| `/status` | 状态；若支持会显示当前模型提供商的用量/配额 |
| `/allowlist` | 列出或增删白名单条目 |
| `/approve allow-once\|allow-always\|deny` | 处理执行审批（exec approval） |
| `/context [list\|detail\|json]` | 解释「上下文」；`detail` 含按文件/工具/技能/系统提示等的大小 |
| `/btw ` | 针对当前会话的 **临时侧问**，不改变后续会话上下文、不写主 transcript（见 [BTW](https://docs.openclaw.ai/tools/btw)） |
| `/export-session [path]` | 导出当前会话为 HTML（含完整 system prompt）；别名 **`/export`** |
| `/whoami` | 显示发送者 ID；别名 **`/id`** |
| `/session idle ` | 管理「聚焦线程绑定」下的 **空闲** 自动 unfocus |
| `/session max-age ` | 管理「聚焦线程绑定」下的 **最大存活时间** 自动 unfocus |
| `/subagents list\|kill\|log\|info\|send\|steer\|spawn` | 查看、控制或派生子代理运行 |
| `/acp spawn\|cancel\|steer\|close\|status\|set-mode\|set\|cwd\|permissions\|timeout\|model\|reset-options\|doctor\|install\|sessions` | 控制 ACP 运行时会话（详见 [ACP Agents](https://docs.openclaw.ai/tools/acp-agents)） |
| `/agents` | 列出与本会话线程绑定的代理 |
| `/focus ` | **Discord**：将当前或新线程绑定到某 session/subagent 目标 |
| `/unfocus` | **Discord**：取消当前线程绑定 |
| `/kill ` | **立即** 中止一个或全部运行中的子代理（无二次确认） |
| `/steer ` | 引导正在运行的子代理；别名 **`/tell `** |
| `/config show\|get\|set\|unset` | 读写磁盘上的 `openclaw.json`；需 `commands.config: true`，通常 **owner-only** |
| `/mcp show\|get\|set\|unset` | 管理 OpenClaw 托管的 MCP 服务配置；需 `commands.mcp: true`，**owner-only** |
| `/plugins list\|show\|get\|install\|enable\|disable` | 发现插件、安装、启停；**`/plugin`** 为别名；写操作需 `commands.plugins: true`；`install` 规格同 `openclaw plugins install` |
| `/debug show\|set\|unset\|reset` | 运行时内存覆盖，不写盘；需 `commands.debug: true`，**owner-only** |
| `/usage off\|tokens\|full\|cost` | 控制每条回复是否附带用量页脚；`cost` 为基于会话日志的本地成本摘要 |
| `/tts ...` | 文字转语音相关（见 [TTS](https://docs.openclaw.ai/tools/tts)）；Discord 原生保留名多为 **`/voice`**，文本通道仍可用 `/tts` |
| `/stop` | 停止当前运行 |
| `/restart` | 重启相关服务（可用 `commands.restart: false` 关闭） |
| `/dock-telegram` / `/dock_telegram` | 将回复路由到 Telegram |
| `/dock-discord` / `/dock_discord` | 将回复路由到 Discord |
| `/dock-slack` / `/dock_slack` | 将回复路由到 Slack |
| `/activation mention\|always` | 群聊中的激活策略（仅群） |
| `/send on\|off\|inherit` | 发送开关；**owner-only** |
| `/reset` 或 `/new [model]` | 新会话；可带模型别名、`provider/model` 或提供商模糊名；无匹配时剩余文字当消息正文 |
| `/think ` | 思考/推理档位等（随模型/提供商变化）；别名 `/thinking`、`/t` |
| `/fast status\|on\|off` | 快模式；省略参数时 `status` 显示当前有效状态 |
| `/verbose on\|full\|off` | 更冗长输出，便于调试；别名 **`/v`** |
| `/reasoning on\|off\|stream` | 推理相关；`on` 时可能单独发 `Reasoning:` 前缀消息；`stream` 为 Telegram 草稿等；别名 **`/reason`** |
| `/elevated on\|off\|ask\|full` | 提升执行权限相关；`full` 跳过 exec 审批；别名 **`/elev`** |
| `/exec host= security= ask= node=` | 查看或设置 exec 相关参数；单发 `/exec` 看当前 |
| `/model ` | 模型选择；别名 **`/models`**；也可使用配置里 `agents.defaults.models.*.alias` 定义的 **`/`** 前缀别名 |
| `/queue ` | 队列行为；可带 `debounce:2s cap:25 drop:summarize` 等；单发 `/queue` 看当前设置 |
| `/bash ` | 主机 shell，等价前缀形式的 **`! `**（需 bash + elevated 白名单） |

---

## 4. 仅文本命令

**在哪里用**：与第 3 节相同，在 **已接入 OpenClaw 的聊天输入框** 中发送。**怎么用**：这些命令往往 **没有** 对应平台「原生 Slash 菜单」，只能靠 **纯文本** 触发；`! ` 仅在开启 `commands.bash` 且授权时可用。

| 命令 | 作用 |
|------|------|
| `/compact [instructions]` | 上下文压缩（见 [compaction](https://docs.openclaw.ai/concepts/compaction)） |
| `! ` | 执行主机 shell（每消息一条）；长任务配合 `!poll` / `!stop` |
| `!poll` | 查看长时间 shell 任务的输出/状态；可选 `sessionId`；**`/bash poll`** 同等 |
| `!stop` | 停止正在运行的 bash 任务；可选 `sessionId`；**`/bash stop`** 同等 |

---

## 5. 指令（Directives）速表

**在哪里用**：仍在 **聊天** 里输入，与第 3 节相同。**怎么用**：可 **单独一条消息只写指令**（会持久到会话并收到确认），也可把指令 **写在普通句子前面** 作临时参数（不持久，见第 1.1 节）。

与第 1.1 节一致；以下为 **作用 + 命令** 对照，便于打印。

| 命令 | 作用摘要 |
|------|----------|
| `/think `（`/thinking`、`/t`） | 模型思考/推理相关选项（提供商相关） |
| `/fast` | 快模式开关或查询状态 |
| `/verbose`（`/v`） | 详细日志级别，调试向 |
| `/reasoning`（`/reason`） | 是否展示/流式推理等 |
| `/elevated`（`/elev`） | 提升执行权限、审批策略 |
| `/exec` | exec 策略参数 |
| `/model`（`/models`、配置的 `/` 别名） | 当前会话模型选择 |
| `/queue` | 消息队列 debounce/cap/drop 等 |

**安全提示**：在 **群聊** 中，`/reasoning` 与 `/verbose` 可能暴露内部推理或工具输出，建议默认关闭。

---

## 6. 频道与原生命令注意事项

**在哪里用**：下表描述的是 **不同聊天平台**（Discord、Slack 等）上，同一斜杠命令在 **原生菜单 vs 纯文本** 下的差异；配置仍在 **`openclaw.json`**（及频道子配置）中。

| 场景 | 说明 |
|------|------|
| Discord 语音 | 原生 **`/vc join|leave|status`**；需 `channels.discord.voice` 与原生命令；**无**对等文本命令 |
| Discord 线程绑定 | `/focus`、`/unfocus`、`/agents`、`/session idle`、`/session max-age` 需启用线程绑定相关配置 |
| Slack | 启用 `commands.native` 时，通常需 **为每个内置命令单独注册** Slack slash；历史单命令 **`/openclaw`** 式仍可能支持 |
| Slack 与 `/status` | Slack **保留** `/status`，原生应注册 **`/agentstatus`**；在 **普通消息** 里文本 **`/status`** 仍可用 |
| 会话键前缀（文档示例） | Discord：`agent::discord:slash:`；Slack：`agent::slack:slash:`（前缀可配置）；Telegram：`telegram:slash:` 等 |
| `/stop` | 针对 **当前聊天会话** 中止当前运行 |
| `/allowlist` 写操作 | `add/remove` 需要 `commands.config=true` 并遵守频道 **`configWrites`** |
| 多账号频道 | `/allowlist --account` 与 `/config set channels..accounts....` 等需遵守目标账号的 `configWrites` |
| 授权与 fast path | 白名单用户 **仅发命令** 的消息可走快速路径（绕过队列与模型）；群聊中纯命令也可绕过 @ 提及要求 |

---

## 7. 常用子功能示例（文档摘录）

以下示例均在 **已与 Bot 建立会话且已授权** 的聊天中发送（若该命令需 `commands.*` 开关，请先在 `openclaw.json` 打开并重启 Gateway）。

### 7.1 `/model`

```
/model
/model list
/model 3
/model openai/gpt-5.2
/model opus@anthropic:default
/model status
```

- `/model` 与 `/model list`：紧凑编号列表。
- Discord 上常有交互式选择器。
- `/model status`：含 endpoint、API 模式等详情（与「用量」不同；用量看 `/status` 或 `openclaw status --usage`）。

### 7.2 `/debug`（需 `commands.debug: true`）

```
/debug show
/debug set messages.responsePrefix="[openclaw]"
/debug unset messages.responsePrefix
/debug reset
```

- 仅 **内存**，不写 `openclaw.json`；`/debug reset` 清除所有覆盖。

### 7.3 `/config`（需 `commands.config: true`）

```
/config show
/config show messages.responsePrefix
/config get messages.responsePrefix
/config set messages.responsePrefix="[openclaw]"
/config unset messages.responsePrefix
```

- 写入前会 **校验**；非法配置会被拒绝。

### 7.4 `/mcp`（需 `commands.mcp: true`）

```
/mcp show
/mcp show context7
/mcp set context7={"command":"uvx","args":["context7-mcp"]}
/mcp unset context7
```

### 7.5 `/plugins`（需 `commands.plugins: true`）

```
/plugins
/plugins list
/plugin show context7
/plugins enable context7
/plugins disable context7
```

- `enable/disable` 只改配置；**安装/卸载** 用 `install` 或终端 `openclaw plugins`；改后通常需 **重启 Gateway**（前台 watched 时可能自动重启）。

### 7.6 `/btw`

```
/btw 我们当前在做什么？
```

- 侧问、不污染主上下文、不写入主 transcript；详见 [BTW](https://docs.openclaw.ai/tools/btw)。

### 7.7 `/tools`

- 回答的是 **运行时** 问题：当前代理在此会话 **此刻** 能用什么。
- 改工具配置请用 Control UI 或配置文件，勿把 `/tools` 当成静态目录。

---

## 8. `openclaw` CLI 一级命令（终端，无前导 `/`）

### 8.1 在哪里用、怎么用

| 项目 | 说明 |
|------|------|
| **在哪里** | 安装有 `openclaw` 的电脑上的 **终端**（本机 shell）。管理的是 **本机** Gateway、配置与插件；远程服务器则需 SSH 登录到那台机器再执行。 |
| **怎么用** | 输入 `openclaw` 加子命令，**不要**加 `/`。例如：`openclaw gateway status`、`openclaw plugins list`。加 `-h` 或 `--help` 查看子命令帮助。 |
| **与聊天的区别** | 聊天里的 `/help` 给 Bot 看；终端里的 `openclaw help` 给 **操作这台机器的人** 看，两者不是同一套入口。 |

全局常用选项：`--dev`、`--profile <name>`、`--container`、`--log-level`、`--no-color`、`-h`、`--version`。

子命令细节请执行：`openclaw <命令> --help`。

| 命令 | 作用 |
|------|------|
| `acp` | Agent Control Protocol：本地 ACP 桥与交互式 client |
| `agent` | 经 Gateway 跑单轮 agent |
| `agents` | 隔离代理：工作区、认证、路由绑定等 |
| `approvals` | 管理 exec 审批（gateway 或 node host） |
| `backup` | 备份/校验 OpenClaw 本地状态归档 |
| `browser` | 专用浏览器（Chrome/Chromium）：快照、点击、截图等 |
| `channels` | 聊天通道：Telegram、Discord、登录、列表等 |
| `clawbot` | 旧版 clawbot 命令别名 |
| `completion` | 生成 shell 补全脚本 |
| `config` | 非交互式 get/set/unset/file/validate；无子命令时常进入引导式 setup |
| `configure` | 交互式配置（凭据、通道、gateway、代理默认值） |
| `cron` | 经 Gateway 调度管理定时任务 |
| `daemon` | Gateway 系统服务（launchd/systemd/schtasks）旧别名 |
| `dashboard` | 用当前 token 打开 Control UI |
| `devices` | 设备配对与 token |
| `directory` | 查联系人/群组 ID 等 |
| `dns` | Tailscale + CoreDNS 等广域发现辅助 |
| `docs` | 搜索线上 OpenClaw 文档 |
| `doctor` | 健康检查与快捷修复 |
| `gateway` | 运行、探测、调用 WebSocket Gateway |
| `health` | 从运行中的 gateway 拉健康状态 |
| `help` | 帮助 |
| `hooks` | 内部 agent hooks 列表/启停/检查 |
| `logs` | 经 RPC 跟踪 gateway 文件日志 |
| `mcp` | 管理 OpenClaw 配置的 MCP 服务（list/show/set/unset） |
| `memory` | 搜索、重建 memory 索引 |
| `message` | 发送/读取消息及频道操作（send、read、react 等） |
| `models` | 发现、扫描、设置默认模型与别名等 |
| `node` | 无头 node host：run/install/status 等 |
| `nodes` | Gateway 管理的 node 配对与远程命令 |
| `onboard` | 交互式 onboarding |
| `pairing` | 安全 DM 配对：列出/批准 |
| `plugins` | 安装/卸载/更新/列出插件与市场 |
| `qr` | iOS 配对 QR/设置码 |
| `reset` | 重置本地配置与状态（CLI 仍保留） |
| `sandbox` | Docker 隔离沙箱容器 |
| `secrets` | 密钥运行时 reload、audit、configure 等 |
| `security` | 本地配置与安全审计 |
| `sessions` | 列出已存会话 |
| `setup` | 初始化本地配置与工作区 |
| `skills` | 列出与查看 skills |
| `status` | 通道健康与最近会话接收方 |
| `system` | 系统事件、心跳、presence |
| `tui` | 连接 Gateway 的终端 UI |
| `uninstall` | 卸载 gateway 服务与本地数据（保留 CLI） |
| `update` | 升级 OpenClaw 与查看更新通道 |
| `webhooks` | Webhook 辅助（如 Gmail Pub/Sub） |

---

## 9. 链接

- 斜杠命令全文：<https://docs.openclaw.ai/tools/slash-commands>
- CLI 索引：<https://docs.openclaw.ai/cli>
- BTW：<https://docs.openclaw.ai/tools/btw>
- TTS：<https://docs.openclaw.ai/tools/tts>
- 压缩上下文：<https://docs.openclaw.ai/concepts/compaction>
- ACP Agents：<https://docs.openclaw.ai/tools/acp-agents>
