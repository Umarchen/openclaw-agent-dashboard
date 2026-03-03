# Claude Code + tmux 使用说明

> 通过 tmux 保持 Claude Code 会话，SSH 断开后回家可继续工作

---

## 一、启动流程（在办公室）

### 1. 新建 tmux 会话

```bash
tmux new -s claude
```

### 2. 窗口 0：启动 ccr Router

```bash
ccr start
```

保持该窗口开着，不要关闭。

### 3. 新建窗口 1

按 **`Ctrl+B`**，松开，再按 **`C`**

### 4. 窗口 1：启动 Claude Code

```bash
cd ~/vrt-projects/projects/openclaw-agent-dashboard   # 或你的工作目录
ccr code --dangerously-skip-permissions
```

### 5. 断开但保持运行（下班时）

按 **`Ctrl+B`**，松开，再按 **`D`**

此时 SSH 可以断开，tmux 里的进程会继续运行。

---

## 二、回家后恢复

### 1. SSH 连接服务器

```bash
ssh 你的服务器
```

### 2. 重新进入 tmux 会话

```bash
tmux attach -t claude
```

### 3. 切换窗口

- **`Ctrl+B` 然后 `0`** → 查看 ccr start
- **`Ctrl+B` 然后 `1`** → 查看 Claude Code

Claude Code 会保持在你离开时的状态，可以直接继续对话。

---

## 三、常用 tmux 快捷键

| 操作 | 按键 |
|------|------|
| 新建窗口 | `Ctrl+B` 然后 `C` |
| 切到窗口 0 | `Ctrl+B` 然后 `0` |
| 切到窗口 1 | `Ctrl+B` 然后 `1` |
| 断开（保持运行） | `Ctrl+B` 然后 `D` |
| 下一个窗口 | `Ctrl+B` 然后 `n` |
| 上一个窗口 | `Ctrl+B` 然后 `p` |

---

## 四、常用命令速查

| 场景 | 命令 |
|------|------|
| 新建 tmux 会话 | `tmux new -s claude` |
| 查看已有会话 | `tmux ls` |
| 恢复会话 | `tmux attach -t claude` |
| 新开 Claude Code | `ccr code --dangerously-skip-permissions` |
| 继续上次对话 | `ccr code -c --dangerously-skip-permissions` |

---

## 五、流程示意

```
办公室：
  tmux new -s claude
  → 窗口0: ccr start
  → Ctrl+B, C 新建窗口1
  → 窗口1: ccr code --dangerously-skip-permissions
  → Ctrl+B, D 断开

回家后：
  ssh 服务器
  → tmux attach -t claude
  → 继续在窗口1里和 Claude 对话
```

---

## 六、前置条件

- 已安装 `@anthropic-ai/claude-code`
- 已安装 `@musistudio/claude-code-router`（智谱 Coding API 需此）
- 已配置 `~/.claude/settings.json`（含 `permissions.defaultMode: "bypassPermissions"` 可跳过权限确认）
