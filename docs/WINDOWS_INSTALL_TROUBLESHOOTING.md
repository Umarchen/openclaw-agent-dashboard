# Windows 安装问题排查指南

本文档针对 `npx openclaw-agent-dashboard@1.0.8 --verbose` 在 Windows 下的安装问题进行说明和解决方案。

---

## 一、问题概览

根据安装日志，主要有以下几类问题：

| 问题 | 严重程度 | 影响 |
|------|----------|------|
| Python 依赖安装失败 | 高 | Dashboard 后端无法启动 |
| Node.js DEP0190 警告 | 低 | 仅提示，不影响功能 |
| 安全模式警告 | 低 | 需配置 `plugins.allow` |

> **v1.0.9+** 已移除 `plugins install` 步骤，openclaw 会自动发现 extensions 下的插件，不再出现「插件注册失败」。

---

## 二、Python 依赖安装失败（核心问题）

### 2.1 错误现象

```
[Errno 11001] getaddrinfo failed
Failed to establish a new connection
ERROR: Could not find a version that satisfies the requirement fastapi==0.109.0
ERROR: No matching distribution found for fastapi==0.109.0
```

### 2.2 根本原因

`[Errno 11001] getaddrinfo failed` 是 **Windows 网络/DNS 解析错误**，表示 pip 无法连接到 PyPI (pypi.org) 下载包。

常见原因：

1. **企业网络限制**：公司防火墙或代理阻止访问 pypi.org
2. **代理未配置**：使用代理上网但 pip 未设置代理
3. **DNS 解析失败**：无法解析 pypi.org 域名
4. **VPN 或网络策略**：限制外网访问

### 2.3 解决方案

#### 方案 A：配置 pip 代理（如有 HTTP/HTTPS 代理）

```powershell
# 临时设置（当前会话）
$env:HTTP_PROXY = "http://代理地址:端口"
$env:HTTPS_PROXY = "http://代理地址:端口"

# 或使用 pip 配置
python -m pip config set global.proxy "http://代理地址:端口"
```

#### 方案 B：使用国内 PyPI 镜像

```powershell
# 使用清华镜像
python -m pip install -r C:\Users\h00427263\.openclaw\extensions\openclaw-agent-dashboard\dashboard\requirements.txt --user -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或阿里云镜像
python -m pip install -r C:\Users\h00427263\.openclaw\extensions\openclaw-agent-dashboard\dashboard\requirements.txt --user -i https://mirrors.aliyun.com/pypi/simple/
```

#### 方案 C：离线安装（完全无外网时）

1. 在有网络的机器上下载依赖：

   ```powershell
   pip download -r requirements.txt -d ./pip-packages
   ```

2. 将 `pip-packages` 目录和 `requirements.txt` 拷贝到目标机器
3. 在目标机器执行：

   ```powershell
   pip install --no-index --find-links=./pip-packages -r requirements.txt --user
   ```

#### 方案 D：跳过 Python 依赖安装

若暂时无法解决网络问题，可先完成插件安装，后续再手动安装：

```powershell
npx openclaw-agent-dashboard@1.0.8 --verbose --skip-python
```

然后等网络恢复后手动执行：

```powershell
python -m pip install -r C:\Users\h00427263\.openclaw\extensions\openclaw-agent-dashboard\dashboard\requirements.txt --user
```

> **注意**：Windows 下若 `python3` 不可用，请使用 `python` 命令。

---

## 三、插件注册（已修复）

**v1.0.9+** 安装流程已优化：仅将文件复制到 `extensions` 目录，不再调用 `openclaw plugins install`。  
openclaw 会自动发现并加载 `extensions` 下的插件，无需手动注册。若仍看到 "plugin already exists" 等提示，请升级到最新版本。

---

## 四、其他警告说明

### 4.1 Node.js DEP0190 警告

```
(node:32244) [DEP0190] DeprecationWarning: Passing args to a child process with shell option true...
```

- **含义**：在 `shell: true` 下传递参数时，Node.js 提示存在潜在安全风险。
- **影响**：当前仅为警告，不影响安装和运行。
- **处理**：可忽略，或等待后续版本改用更安全的调用方式。

### 4.2 安全模式警告

```
WARNING: Plugin "openclaw-agent-dashboard" contains dangerous code patterns: Shell command execution detected (child_process)
plugins.allow is empty; discovered non-bundled plugins may auto-load
```

- **含义**：插件使用了 `child_process` 执行命令，被识别为“危险模式”。
- **影响**：插件可能被当作未受信任代码，需要显式允许。
- **处理**：在 openclaw 配置中设置 `plugins.allow: ["openclaw-agent-dashboard"]`。

---

## 五、推荐安装流程（Windows + 企业网络）

1. **删除旧版本（若存在）**：

   ```powershell
   Remove-Item -Recurse -Force "$env:USERPROFILE\.openclaw\extensions\openclaw-agent-dashboard" -ErrorAction SilentlyContinue
   ```

2. **使用国内镜像安装**：

   ```powershell
   npx openclaw-agent-dashboard@1.0.8 --verbose --skip-python
   ```

3. **手动安装 Python 依赖（使用镜像）**：

   ```powershell
   python -m pip install -r "$env:USERPROFILE\.openclaw\extensions\openclaw-agent-dashboard\dashboard\requirements.txt" --user -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

4. **配置 openclaw 信任插件**（如仍有警告）：

   编辑 `%USERPROFILE%\.openclaw\config.json`，添加：

   ```json
   {
     "plugins": {
       "allow": ["openclaw-agent-dashboard"]
     }
   }
   ```

5. **验证**：执行 `openclaw tui`，Dashboard 应自动启动，访问 http://localhost:38271。

---

## 六、后续改进建议（项目维护者）

1. **Python 安装**：支持通过环境变量或参数指定 pip 镜像（如 `PIP_INDEX_URL`）。
2. **帮助信息**：在 Windows 下增加代理、镜像、离线安装的说明。
3. **runCommand**：考虑使用 `execSync(cmd, args, { shell: false })` 或 `spawn` 传参，消除 DEP0190 警告。
