# Windows 安装

按顺序做即可。全程用 **PowerShell**（开始菜单搜「PowerShell」打开）。

---

## 第 0 步：第一次用电脑装这些（只做一次）

1. 安装 **[Node.js](https://nodejs.org/)**（选 LTS，一路下一步）。
2. 安装 **[Python 3](https://www.python.org/downloads/)**，**务必勾选「Add Python to PATH」**，再点安装。
3. 打开 PowerShell，装 OpenClaw：
   ```powershell
   npm install -g openclaw
   ```

不确定装没装好？在 PowerShell 里分别执行 `node -v`、`python --version`、`openclaw --version`，都能出版本号就行。  
若只有 `py -3 --version` 能用，可到「系统 → 环境变量」里加一个 **`PYTHON_CMD`**，值为 `py`（一般不必，多数人选对 PATH 即可）。

---

## 第 1～3 步：装插件（每次新装 / 换电脑按这个来）

**1. 装插件**

```powershell
openclaw plugins install openclaw-agent-dashboard@latest
```

看到安装成功即可。过程中若有 **child_process**、**plugins.allow** 之类警告，**一般不用管**。

**2. 装 Python 依赖（必做，和 Linux 一样要多这一步）**

```powershell
$plugin = "$env:USERPROFILE\.openclaw\extensions\openclaw-agent-dashboard"
node "$plugin\scripts\install-python-deps.js" $plugin --verbose
```

等它跑完，不要报错就行。

**3. 重启网关**

```powershell
openclaw gateway restart
```

**4. 打开浏览器**

访问：**http://localhost:38271**

---

## 还不行？

| 情况 | 怎么办 |
|------|--------|
| 第 2 步失败（网络、pip） | 看 [WINDOWS_INSTALL_TROUBLESHOOTING.md](./WINDOWS_INSTALL_TROUBLESHOOTING.md) |
| 提示 **plugin already exists** | 看仓库根目录 [README.md](../README.md) 里「从 path / 旧版安装迁移到 npm」 |
| 想手动装 Python 依赖 | 见下文 **cmd 三行** |

插件默认在：`C:\Users\你的用户名\.openclaw\extensions\openclaw-agent-dashboard`。  
若你改过 OpenClaw 数据目录，把上面命令里的路径换成你机器上真实的 `extensions\openclaw-agent-dashboard`。

**cmd 三行（手动 Python 依赖）：**

```cmd
cd %USERPROFILE%\.openclaw\extensions\openclaw-agent-dashboard\dashboard
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## 开发者 / 其它方式（可选）

- **从源码**：`git clone` 后进目录执行 `npm run deploy`，再 `openclaw gateway restart`。  
- **更多说明**：根目录 [README.md](../README.md)。
