# OpenClaw Agent Dashboard：插件侧热重载/被动 Kill 恢复 — 需求与分析方案（评审稿）

**范围**：仅本仓库插件侧（以 `plugin/index.js` 为主）；**平台 / Gateway / OpenClaw 加载行为不可修改**。

**版本**：草案，供评审  
**关联代码**：`plugin/index.js`（`startDashboard` / `stopDashboard` / `reclaimStaleOurDashboardPort` / 端口探测）

---

## 1. 背景与问题陈述

本插件在 **Gateway 进程内** 检测 `OPENCLAW_GATEWAY_PORT` 后拉起 Python（uvicorn）Dashboard。当 **Gateway 不重启**，仅发生 **插件被 kill、卸载重载** 等非「整进程重启」场景时，偶发 **Dashboard 子进程再也起不来**。

结合当前实现，主要风险包括：

- 启动路径中存在 **异步 `portPromise`**（**未被 `await`，仅以 `.then()` 衔接**）与 **`isPortInUse` 为真则直接跳过启动** 的逻辑；在 `stop()` 与异步选口/启动交错时，会出现 **stop 之后仍执行 spawn** 等隐蔽竞态（见 **§7.1**）。
- **`dashboardProcess` 为模块级变量**，热重载下 **Node `require` 缓存语义** 会导致「僵尸引用 / 孤儿进程」与插件侧状态脱节（见 **§7.2**）。
- 在 `stop()` 刚结束子进程后，端口可能仍处于 **尚未完全释放** 或 **旧实例仍短暂监听** 的窗口；**spawn 到 uvicorn 真正 listen** 之间存在 **数百毫秒～数秒** 的空窗，快速 **start→stop→start** 可能叠加 **双实例** 误判（见 **§7.3**）。
- `reclaimStaleOurDashboardPort` 依赖 **`http://127.0.0.1:<port>/api/version`** 判断是否为本插件；在进程刚退出、半死或竞态下，探测可能 **不足以触发回收**，随后出现 **端口仍被判定占用 + 跳过 spawn** → 表现为「插件起不来」。
- **TCP `TIME_WAIT`** 与 **短重试总时长** 不匹配时，可能出现「逻辑上已释放监听、但绑定仍失败」的窗口；是否与 **SO_REUSEADDR**（及 uvicorn/Starlette 默认行为）协同需在方案中写明（见 **§7.4**）。

**约束**：上游 **不提供** 生命周期顺序保证或 API 扩展时，只能通过 **本插件** 降低失败率。

---

## 2. 目标与非目标

### 2.1 目标

- 在 **Gateway 长期存活** 的前提下，对 **插件被动卸载/重载/kill 子进程** 等场景，使 Dashboard **以高概率自动恢复可用**，行为可预期、日志可排障。
- 不将「用户必须重启 Gateway」作为 **唯一** 恢复手段（文档中仍可保留为兜底建议）。

### 2.2 非目标

- 不改变 OpenClaw 插件 API 约定、不要求上游新增 hook。
- 不承诺覆盖所有极端情况（如系统资源耗尽）；聚焦 **常见热重载竞态**。
- 默认 **优先** 仅改 `plugin/index.js`；若 **`TIME_WAIT` / `SO_REUSEADDR`** 或 **就绪探测** 必须依赖 Python 启动参数或中间件，再 **单独立项** 最小改动（见 **§7.4、§7.3**）。

---

## 3. 需求说明

### 3.1 功能需求

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-1 | 插件 **`stop()`** 被调用时，应 **尽力终止** 本插件拉起的 Dashboard 子进程，并 **缩小**「stop 已返回但端口仍被旧实例占用」的时间窗（例如等待子进程 exit，或带超时的等待后再返回）。 | P0 |
| FR-2 | 在 **`portPromise` 完成后的启动阶段**：若目标端口 **已被占用**，不得 **仅因占用就永久放弃启动**；应 **先区分**「本插件 Dashboard / 其他服务 / 释放中」，并执行 **有限次退避重试**。 | P0 |
| FR-3 | 若占用方可通过现有机制识别为 **本插件 Dashboard**（`/api/version` 中 `name` 与清单一致），应 **与 `reclaimStaleOurDashboardPort` 策略一致或复用**（SIGTERM → 必要时 SIGKILL / Linux fuser 等），再尝试 bind/spawn。 | P0 |
| FR-4 | 在 **非用户显式固定默认端口** 的策略下，若首选端口长期不可用，**允许在有限范围内选择备用端口**（与现有 `findAvailablePort` 一致或可配置），日志须打印 **实际监听端口**。 | P1 |
| FR-5 | 对 **用户显式固定端口**：若端口被占且 **可证明为本插件旧实例**，应回收；若 **不可证明且非本服务**，**不得误杀**；应 **重试 + 清晰告警**；最终失败时日志说明原因。 | P0 |
| FR-6 | 关键分支（跳过、回收、重试、spawn 成功/失败）使用 **统一、可 grep 的日志前缀**（如现有 `[OpenClaw-Dashboard]`），便于线上排障。 | P1 |
| FR-7 | **`portPromise` 与 `stop()` 交错**：须引入 **世代号 / 中止令牌**（或等效机制），保证 **`stop()` 生效后**，此前已发起且仍 pending 的选口/启动链 **不得再 spawn** 新子进程（见 **§7.1**）。 | P0 |
| FR-8 | **模块热重载语义**：须显式考虑 **同一 `require` 缓存** 下 `dashboardProcess` 与真实进程不一致、以及 **重新 `require` 后旧子进程脱离引用** 的情况；通过 **就绪探测、版本探针 reclaim、可选 PID/父进程标记文件** 等组合降低孤儿与误判（见 **§7.2**）。 | P0 |
| FR-9 | **`spawn` 至 listen 就绪空窗**：在 **连续快速 start/stop/start** 场景下，须防止 **双实例**（例如 spawn 后 **轮询 `/api/version` 或端口 listen** 直至成功/超时；与 **FR-7** 串行化「一次仅一条启动链」协同）（见 **§7.3**）。 | P0 |

### 3.2 非功能需求

| ID | 描述 | 优先级 |
|----|------|--------|
| NFR-1 | 重试具备 **上限**（次数与/或总时长），避免长时间阻塞。 | P0 |
| NFR-2 | **Linux**：保持/增强现有 reclaim 能力。**Windows**：`getListenPidsOnPort` 当前返回空数组 → **无法按 PID 精确 reclaim**；策略上 **禁止凭猜测杀进程**；恢复路径建议为：**依赖备用端口（FR-4）**、**用户显式重启 Gateway**、或 **仅当 HTTP 探针能证明为本插件且具备安全 kill 手段时** 才回收（若未来补齐 Windows 端口→PID 方案再评审）（见 **§7.5**）。 | P1 |
| NFR-3 | 代码改动 **优先仅限** `plugin/index.js`；避免无关重构。 | P0 |

---

## 4. 技术分析与方案概述

### 4.1 根因归纳（插件视角）

1. **「端口占用 ⇒ 可能已在运行 ⇒ 跳过启动」** 在热重载场景下过于激进；占用更常表示 **释放中** 或 **待回收的本插件监听**，而非健康实例已存在。
2. **`stop()` 与子进程退出 / 端口释放** 之间缺少 **同步或超时等待**，放大竞态窗口。
3. **`portPromise` 未被顶层 `await`**，`stop()` 可能在选口/reclaim 仍 pending 时执行，**`.then()` 仍随后 spawn** → **stop 后又起新实例**（**§7.1**）。
4. **模块级 `dashboardProcess` + `require` 缓存**：热重载下 **陈旧引用或孤儿进程**（**§7.2**）。
5. **回收逻辑** 与 **spawn 前检查** 若不一致，会出现「未回收但启动被跳过」的断层。
6. **`spawn` 到 listen 的延迟** 与快速重入组合，可能 **双实例** 或状态错乱（**§7.3**）。

### 4.2 方案原则

- **占用 ≠ 健康**：「端口被占」须进入 **探测 → 决策**（本插件 / 非本插件 / 未知），禁止单分支永久 return。
- **stop 收口**：`stop()` 内 **signal + 等待 exit（带超时）**，减少与下一轮 `start` 的重叠。
- **start 韧性**：spawn 前 **有限重试**（退避 + 总时长上限），每轮可重新执行 `probe` / `reclaim` / 占用检测。
- **不误杀**：仅在有 **强证据**（现有 version 探针；评审可议是否增加辅助手段）表明为本插件 Dashboard 时执行 kill。
- **异步链可撤销**：任何在 `portPromise` 之后的逻辑，在 **执行 spawn 前** 必须校验 **当前世代 / 未中止**，否则直接退出（**§7.1**）。
- **spawn 后就绪**：子进程已创建不等于端口可服务；必要时 **短轮询就绪** 再宣告成功或允许下一轮逻辑（**§7.3**）。

### 4.3 建议流程（评审用伪代码）

```
// 模块级：generation 单调递增；stop 时 bump + 标记 aborted
stop():
  bump generation, set aborted for in-flight start chain
  if child:
    SIGTERM → await exit(timeout T1) → 若仍存活则 SIGKILL → await exit(timeout T2)
  clear child ref

start (port 已选定后，携带 startGeneration):
  repeat ≤ N 次且总耗时 ≤ T_total:
    if startGeneration != currentGeneration: return   // 已被 stop 作废
    if port free:
      spawn
      if generation 仍有效:
        await listen-ready(/api/version 或等价, timeout T_ready)
          → 成功: success
          → 超时: kill 该子进程 → backoff → continue   // 本轮失败，与 §7.3、FR-9 对齐
      else:
        return
    if port in use:
      if probeOurDashboard:
        reclaim (与现有逻辑一致) → backoff → continue
      else:
        backoff → continue   // TIME_WAIT / 其他服务 / 抖动；见 §7.4
  log 明确失败原因并 return
```

### 4.4 与现有实现的衔接点

- **`stopDashboard`**：由「仅 kill + 立即置 null」增强为 **带超时的子进程退出等待**（若 OpenClaw `stop` 仅为同步 API，则采用 **同步轮询 + 上限** 的可行实现）。
- **`portPromise.then` 中 `isPortInUse` 即 return 的逻辑**：替换为 **重试 + 探测 + 回收** 流程，避免「一次占用永久跳过」。
- **`portPromise` 生命周期**：与 **`stop()` 世代/中止令牌** 绑定；`.then` 入口与 **spawn 前** 双重校验，避免 **stop 后仍 spawn**（**§7.1**）。

### 4.5 风险与对策

| 风险 | 对策 |
|------|------|
| stop 阻塞过久 | **总超时**；超时后记录 warn，由 start 侧重试 |
| 误杀第三方服务 | 仅 version **name 匹配** 才 reclaim；无证据不 kill |
| 双实例 | **FR-7 世代号** + spawn 前检查 `dashboardProcess` + **spawn 后就绪探测（FR-9）**；回收范围限定为已证实为本插件的监听者 |
| `portPromise` pending 时 stop | **世代/中止**；旧链不 spawn |
| 模块重载孤儿进程 | **HTTP 探针 reclaim**、可选 **数据目录 pid 文件**（写入 Gateway PID + 子 PID；**PID 仅辅助线索**，杀进程前须 **`/api/version` 二次确认**，见 **§7.2**） |
| `TIME_WAIT` 导致短重试全失败 | **核实 uvicorn/bind 是否已 SO_REUSEADDR**；不足则 **Python 侧最小改动** 或 **延长重试/换备用端口策略**（**§7.4**） |
| Windows 无 PID reclaim | **备用端口** + 文档化兜底；**不盲杀**（**§7.5**） |

### 4.6 建议验收标准

1. **模拟**：Gateway 不重启，连续触发插件 unload/load（或等效 stop→start），**10 次中 ≥9 次** HTTP 可访问（含落在备用端口的情形，日志须可见端口）。
2. **第三方占用端口**：非本插件 `name` 时 **不执行 SIGKILL**；日志说明占用与失败/策略。
3. **日志**：失败路径包含 **端口、重试序号/上限、判定结果**（our / other / unknown）。

---

## 5. 待评审决议项

1. **OpenClaw `stop` 与再次 `load` 的顺序**：若 **不保证** stop 返回后才 load，是否引入 **文件锁/单例** 串行化同数据目录启动（复杂度高，需单独评审）。
2. **重试参数**：`N`、总时长、退避间隔 **写死** 还是 **config.json / 环境变量** 可配置。
3. **显式固定端口**：占用且非本插件时，是 **硬失败** 还是 **允许自动换端口**（涉及用户预期，需产品确认）。
4. **`TIME_WAIT` 策略**：是否接受 **Python/uvicorn 侧** 增加或确认 **`SO_REUSEADDR`**（及是否与 `SO_REUSEPORT` 混淆风险评审）；若坚持 **仅 JS**，则 **备用端口 / 更长重试** 的取舍。
5. **Windows**：是否在 **无 PID** 前提下，将 **「自动换端口 + 醒目标志日志」** 定为默认恢复路径。

---

## 6. 文档与代码路径

- **本文档**：`docs/review-plugin-dashboard-hot-reload.zh-CN.md`
- **实现落点（评审通过后）**：`plugin/index.js`（必要时 **极小范围** `dashboard` Python 启动配置，见 §7.3–§7.4）

评审通过后，按本文档 FR/NFR 拆任务实现，并视需要补充最小化自测步骤或脚本说明（不强制扩展文档范围）。

---

## 7. 评审补充：遗漏与可深化点（纳入修订）

本节吸纳评审意见，便于与 §3–§5 对照实现与验收。

### 7.1 `portPromise` 未被 `await` 的隐蔽竞态

**现状**（`plugin/index.js` 约 320–323 行）：`portPromise` 由异步 IIFE 产生，**主流程不 await**，仅通过 `.then()` 在将来执行 `spawn`。

**后果**：若 `stop()` 在 `portPromise` 仍 **pending**（例如仍在 `reclaimStaleOurDashboardPort` 或 `findAvailablePort`）时被调用：

- `stopDashboard` 可能此时 **`dashboardProcess` 仍为 null**（子进程尚未创建），`stop` 对子进程几乎无操作；
- 之后 **`portPromise.then` 仍会运行**，并在条件满足时 **再次 `spawn`** → 出现 **「已 stop 却又启动新实例」** 或与下一轮 `start` **交错双起** 的风险。

**方案补充**：除 **§4.3** 的世代号/中止令牌外，可选增强包括：**将选口 + reclaim + spawn 纳入同一条可取消链**（如 `AbortController` 风格标志位），在 `stop()` 中置位；**`.then` 第一行与 `spawn` 前** 均检查标志位与世代一致性。

### 7.2 模块级 `dashboardProcess` 与 Node `require` 缓存语义

**现状**（约 22 行）：`let dashboardProcess = null` 为 **模块级**状态。

**热重载时两种典型情况**：

| 情形 | 可能现象 |
|------|----------|
| **复用同一 `require` 缓存** | `dashboardProcess` 仍指向 **已退出或被外部 kill** 的子进程句柄；变量非 null 但进程已僵尸，**管理逻辑失真**。 |
| **重新 `require` 新模块实例** | 新实例中 `dashboardProcess === null`，但 **旧子进程仍在运行**，成为 **孤儿**，插件侧 **失去 kill 与编排能力**。 |

**方案补充**：文档 **FR-8** 要求设计显式考虑上述语义；实现上可与 **HTTP `/api/version` + reclaim**、可选 **`~/.openclaw-agent-dashboard`（或既有数据目录）下写入 `{ gatewayPid, childPid, port, startedAt }`** 结合：新实例启动前读文件，若 **端口被占且能证明为本插件** 则 reclaim，若 **父 PID 非当前 Gateway** 则谨慎处理（避免误杀其他用户会话，需与产品约束对齐）。

**注意（PID 文件陈旧与复用）**：PID 文件仅作 **辅助线索**；进程退出后 **同一 PID 可能被操作系统复用** 给无关进程。任何基于文件中 `childPid` 的 reclaim 或杀进程决策，**使用前仍须通过 `/api/version` 探针二次确认** 为本插件 Dashboard，避免因 PID 复用 **误杀无关进程**。（与上文「能证明为本插件」一致，此处显式写出更安全。）

### 7.3 Python 端启动延迟与「尚未 listen」窗口

**事实**：`spawn()` 成功仅表示 Node 侧创建了子进程；**解释器启动 + import 依赖 + uvicorn bind** 往往还需 **数百毫秒～数秒**。此窗口内：

- **`isPortInUse` 可能为 false**（尚未监听）——与「未启动」难以区分；
- 若 **极短间隔**内再次 `start`（或 **§7.1** 的旧 `.then` 与新一轮 `start` 重叠），可能出现 **两个子进程先后绑定同一策略端口**，或 **逻辑上认为未起而又起一套**。

**方案补充**（对应 **FR-9**）：

- **`spawn` 之后**增加 **就绪等待**：如对 `http://127.0.0.1:<port>/api/version` **短轮询**直至成功或超时；超时则 **终止该子进程** 并进入重试/失败分支。
- 与 **FR-7** 配合：同一时刻 **仅允许一条「从选口到就绪确认」的启动链** 生效。

### 7.4 `TIME_WAIT` 与 `SO_REUSEADDR`

**背景**：在 Linux 上，主动关闭方可能使本地地址端口进入 **`TIME_WAIT`**（常见讨论值为 **约 60s 量级**，具体以内核与套接字选项为准）。若插件侧重试总时长 **远小于** 该窗口，可能出现 **「进程已死，但绑定仍失败」** 的假象，导致短重试 **全部失败**。

**说明**：服务端 **主动 `listen` 时设置 `SO_REUSEADDR`** 通常可 **在 `TIME_WAIT` 期间重新绑定同一端口**（行为与平台相关，需验证）。常见 ASGI/uvicorn 栈 **可能默认已开启**，**实现前应在当前 `uvicorn` 版本与启动方式下核实**（若未设置，可在 **Python 启动路径** 做 **最小改动** 传入等价配置，作为独立任务评审）。

**文档要求**：方案中须 **显式记录**「依赖短重试 / 依赖 reuse / 或依赖换端口」中的取舍，避免评审假设「几秒重试必能抢回原端口」。

### 7.5 Windows 平台策略（具体化）

**现状**（约 200–201 行）：`getListenPidsOnPort` 在 Windows **返回空数组**，**无法**像 Unix 一样通过 **lsof 式 PID** 做精确 reclaim；**盲杀端口占用进程风险极高**。

**建议默认策略（插件侧可落地）**：

1. **禁止**在无 **HTTP 级证据**（`/api/version` 且 `name` 匹配）时执行 **系统级 kill**。
2. 若 **能证明**监听者为本插件 Dashboard，但 **仍无法安全结束进程**（无 PID 手段）：**记录明确错误日志**，并建议用户 **重启 Gateway** 或 **手动结束进程**（文档/README 已有类似说明可交叉引用）。
3. 对 **非显式固定端口** 场景：优先 **自动递增备用端口**（与现有 `findAvailablePort` 思路一致），保证 **「至少有一个可访问实例」**，并在日志中用 **醒目标记** 打印实际 URL，避免用户误以为仍在原端口。

---

**修订记录**：根据评审意见增补 §1、§3、§4、§5 及全文 **§7**（`portPromise` 竞态、模块缓存、`spawn` 延迟、`TIME_WAIT`/reuse、Windows 策略）。后续微调：**§7.2** 补充 PID 复用与 **`/api/version` 二次确认**；**§4.3** 伪代码补充 **listen-ready 超时则 kill 子进程并退避重试**，与 **§7.3、FR-9** 对齐。
