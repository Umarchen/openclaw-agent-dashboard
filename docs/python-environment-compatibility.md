# Python 环境兼容性说明

## 问题背景

不同用户的操作系统、Python 发行版、包管理策略各不相同，安装 Python 依赖时可能遇到：

| 场景 | 系统/环境 | 典型错误 | 原因 |
|------|-----------|----------|------|
| **PEP 668** | Debian 12、Ubuntu 23.04+、Fedora 38+ | `externally-managed-environment` | 系统 Python 被标记为「外部管理」，禁止全局 pip 安装 |
| **无 pip** | Debian/Ubuntu 最小安装 | `python3: No module named 'pip'` | 未安装 `python3-pip` |
| **无 venv** | 部分发行版 | `No module named 'venv'` | 未安装 `python3-venv`（与 python3 分开打包） |
| **pyenv/conda** | 用户自建环境 | 行为各异 | 非系统 Python，可能有不同限制 |
| **Windows** | 各版本 | `python3` 可能不存在 | 通常用 `python` 或 `py` |
| **macOS** | Homebrew / 系统 Python | 行为各异 | Homebrew Python 可能有类似限制 |

## 业界推荐做法

根据 [PEP 668](https://peps.python.org/pep-0668/)、[Python Packaging User Guide](https://packaging.python.org/)：

1. **venv（虚拟环境）**：项目/应用专属依赖，完全隔离，**不受 PEP 668 影响**，跨平台一致
2. **pipx**：适合独立 CLI 工具，每个工具一个隔离环境
3. **pip --user**：兜底方案，在 PEP 668 环境下可用，但可能与用户其他包冲突

## 本插件的策略

采用 **venv 优先，pip --user 兜底**：

```
1. 尝试在插件目录创建 .venv，安装依赖（推荐，无 PEP 668 问题）
2. 若 venv 失败（如缺 python3-venv），回退到 pip --user 链
3. 运行时优先使用 .venv/bin/python（Unix）或 .venv/Scripts/python.exe（Windows）
```

### 安装阶段（install-plugin.sh）

- 优先：`python3 -m venv $PLUGIN_PATH/dashboard/.venv` → `pip install -r requirements.txt`
- 兜底：`python3 -m pip install -r ... --user`（及 pip/pip3 变体）

### 运行阶段（plugin/index.js）

- 优先：`$PLUGIN_PATH/dashboard/.venv/bin/python`（Unix）或 `.../Scripts/python.exe`（Windows）
- 兜底：`PYTHON_CMD` 或 `python3`

## 用户自助排查

若安装失败，可按系统执行：

**Debian / Ubuntu：**
```bash
sudo apt install python3-pip python3-venv
```

**Fedora：**
```bash
sudo dnf install python3-pip
```

**手动安装依赖（跳过 venv）：**
```bash
python3 -m pip install -r ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard/requirements.txt --user
```
