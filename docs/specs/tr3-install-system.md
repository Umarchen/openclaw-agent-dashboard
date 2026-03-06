# TR3: 安装系统技术需求分析

> 版本: 1.0
> 日期: 2026-03-06
> 状态: 待审核

---

## 一、背景与目标

### 1.1 当前问题

| 问题 | 影响 |
|------|------|
| 用户需要 `git clone` + `npm run deploy` | 门槛高，需要 Node/npm 环境 |
| 需要本地构建前端 | 构建时间长，依赖 Node 生态 |
| 安装脚本耦合度高 | `install-plugin.sh` 包含构建、打包、安装全流程 |
| 无版本管理 | 无法指定安装特定版本 |

### 1.2 目标

1. **用户体验**：一条命令完成安装，无需 Node/npm/构建环境
2. **版本控制**：支持安装指定版本或最新版本
3. **跨平台**：支持 Linux、macOS、Windows（Git Bash）
4. **开发者友好**：保留从源码安装的能力

---

## 二、系统架构

### 2.1 整体流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        安装入口                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   curl | bash install.sh          ./install-plugin.sh           │
│   (普通用户)                        (开发者)                      │
│         │                                │                      │
│         ▼                                ▼                      │
│   ┌─────────────┐               ┌─────────────┐                │
│   │ 下载预构建包 │               │ 本地构建打包 │                │
│   │ (GitHub/CDN)│               │ npm run pack│                │
│   └──────┬──────┘               └──────┬──────┘                │
│          │                              │                       │
│          ▼                              ▼                       │
│   ┌─────────────────────────────────────────────┐              │
│   │         openclaw plugins install *.tgz       │              │
│   └──────────────────────┬──────────────────────┘              │
│                          │                                     │
│                          ▼                                     │
│   ┌─────────────────────────────────────────────┐              │
│   │       install-python-deps.sh (可选)          │              │
│   │         安装 Python 后端依赖                  │              │
│   └─────────────────────────────────────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 文件结构

```
scripts/
├── install.sh              # 入口脚本：curl | bash 一键安装
├── install-plugin.sh       # 开发者脚本：从源码安装（保留）
├── install-python-deps.sh  # Python 依赖安装（新增，从 install-plugin.sh 抽取）
├── build-plugin.js         # 构建脚本（不变）
├── bundle.sh               # 离线打包（不变）
└── release-pack.sh         # 发布打包（新增）

.github/workflows/
└── release.yml             # CI 发布流程（新增）
```

---

## 三、组件详细设计

### 3.1 预构建包 (Pre-built Package)

#### 3.1.1 包格式

| 项目 | 规格 |
|------|------|
| 格式 | `.tgz` (tarball) |
| 命名 | `openclaw-agent-dashboard-v{VERSION}.tgz` |
| 大小 | ~130KB (压缩后) |
| 平台 | 跨平台通用 (无二进制依赖) |

#### 3.1.2 包内容

```
openclaw-agent-dashboard-v1.0.0.tgz
└── package/
    ├── openclaw.plugin.json    # 插件元数据
    ├── package.json            # npm 包信息
    ├── index.js                # 插件入口 (Node.js)
    ├── dashboard/              # Python 后端
    │   ├── main.py
    │   ├── requirements.txt
    │   ├── api/
    │   ├── data/
    │   └── ...
    └── frontend-dist/          # 前端构建产物
        ├── index.html
        └── assets/
```

#### 3.1.3 生成方式

```bash
# scripts/release-pack.sh
npm run pack                    # 构建前端 + 复制文件到 plugin/
cd plugin && npm pack           # 生成 tgz
mv *.tgz ../openclaw-agent-dashboard-v${VERSION}.tgz
```

#### 3.1.4 发布渠道

| 渠道 | URL 格式 |
|------|----------|
| GitHub Releases (主) | `https://github.com/{owner}/{repo}/releases/download/v{VERSION}/openclaw-agent-dashboard-v{VERSION}.tgz` |
| 自定义 CDN (备) | `https://cdn.example.com/openclaw-agent-dashboard-v{VERSION}.tgz` |

---

### 3.2 install.sh (入口脚本)

#### 3.2.1 功能规格

| 功能 | 说明 |
|------|------|
| 系统检测 | Linux / macOS / Windows (Git Bash) |
| 前置检查 | openclaw CLI 是否已安装 |
| 版本解析 | 支持指定版本或获取最新版本 |
| 下载 | curl / wget 自动选择 |
| 安装 | 调用 `openclaw plugins install` |
| Python 依赖 | 调用 `install-python-deps.sh` |

#### 3.2.2 命令行接口

```bash
# 默认安装最新版本
curl -fsSL https://raw.githubusercontent.com/{owner}/{repo}/main/scripts/install.sh | bash

# 指定版本
DASHBOARD_VERSION=1.0.0 bash install.sh

# 使用自定义下载源
DASHBOARD_RELEASE_URL=https://cdn.example.com/xxx.tgz bash install.sh

# 调试模式
VERBOSE=1 bash install.sh

# 预览模式
DRY_RUN=1 bash install.sh
```

#### 3.2.3 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DASHBOARD_VERSION` | `latest` | 安装版本 |
| `DASHBOARD_RELEASE_URL` | - | 完整下载 URL (覆盖版本) |
| `DASHBOARD_SKIP_PYTHON` | `0` | 跳过 Python 依赖安装 |
| `VERBOSE` | `0` | 显示详细输出 |
| `DRY_RUN` | `0` | 预览模式 |

#### 3.2.4 流程伪代码

```bash
main() {
  # 1. 检测系统
  OS=$(detect_os)
  validate_os "$OS"

  # 2. 检查 openclaw
  check_command openclaw "npm install -g openclaw"

  # 3. 解析版本
  VERSION=$(resolve_version "${DASHBOARD_VERSION:-latest}")

  # 4. 构建下载 URL
  DOWNLOAD_URL=$(build_download_url "$VERSION")

  # 5. 下载到临时目录
  TMP_DIR=$(mktemp -d)
  TGZ_FILE="$TMP_DIR/openclaw-agent-dashboard.tgz"
  download_file "$DOWNLOAD_URL" "$TGZ_FILE"

  # 6. 清理旧安装
  cleanup_old_installation

  # 7. 安装插件
  openclaw plugins install "$TGZ_FILE"

  # 8. 安装 Python 依赖
  if [ "$DASHBOARD_SKIP_PYTHON" != "1" ]; then
    install_python_deps "$PLUGIN_PATH"
  fi

  # 9. 清理临时文件
  rm -rf "$TMP_DIR"

  # 10. 输出成功信息
  print_success_message
}
```

#### 3.2.5 版本解析逻辑

```bash
resolve_version() {
  local requested="$1"

  if [ "$requested" = "latest" ]; then
    # 方案 A: 使用 GitHub API (有速率限制)
    # curl -s https://api.github.com/repos/{owner}/{repo}/releases/latest | jq -r .tag_name

    # 方案 B: 使用 GitHub 重定向 (推荐，无速率限制)
    local latest_url="https://github.com/{owner}/{repo}/releases/latest"
    local release_page
    release_page=$(curl -fsSL "$latest_url" 2>/dev/null)
    # 从页面提取版本号或使用重定向 URL
    echo "$latest_version"
  else
    echo "$requested"
  fi
}
```

#### 3.2.6 清理逻辑

```bash
cleanup_old_installation() {
  local plugin_dir="${OPENCLAW_CONFIG_DIR}/extensions/openclaw-agent-dashboard"

  # 尝试卸载配置记录
  openclaw plugins uninstall openclaw-agent-dashboard --force 2>/dev/null || true

  # 删除物理目录 (uninstall 不删除目录)
  if [ -d "$plugin_dir" ]; then
    rm -rf "$plugin_dir"
  fi
}
```

---

### 3.3 install-python-deps.sh

#### 3.3.1 功能

从 `install-plugin.sh` 抽取 Python 依赖安装逻辑，供多个入口复用。

#### 3.3.2 接口

```bash
# 用法
./scripts/install-python-deps.sh <plugin_dir> [options]

# 示例
./scripts/install-python-deps.sh ~/.openclaw/extensions/openclaw-agent-dashboard
./scripts/install-python-deps.sh ~/.openclaw/extensions/openclaw-agent-dashboard --verbose
```

#### 3.3.3 参数

| 参数 | 说明 |
|------|------|
| `$1` | 插件安装目录 (必须) |
| `--verbose` | 显示详细输出 |
| `--venv-only` | 仅使用 venv，不回退 pip |
| `--skip-create` | 跳过创建 venv (已存在) |

#### 3.3.4 安装策略

```
策略 1: venv (推荐)
├── python3 -m venv .venv
├── .venv/bin/pip install -r requirements.txt
└── 优点: 隔离环境，不受 PEP 668 影响

策略 2: pip --user (回退)
├── python3 -m pip install -r requirements.txt --user
└── 优点: 无需 venv 支持

策略 3: 系统 pip (最后回退)
├── pip install -r requirements.txt
└── 适用于有权限的环境
```

---

### 3.4 release-pack.sh

#### 3.4.1 功能

生成预构建包，供 CI 或本地发布使用。

#### 3.4.2 流程

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

# 1. 读取版本
VERSION=$(jq -r '.version' "$ROOT/plugin/openclaw.plugin.json")
OUTPUT_FILE="$ROOT/openclaw-agent-dashboard-v${VERSION}.tgz"

# 2. 确保已构建
if [ ! -d "$ROOT/plugin/frontend-dist" ]; then
  npm run pack
fi

# 3. 生成 tgz
cd "$ROOT/plugin"
npm pack

# 4. 重命名并移动
mv openclaw-agent-dashboard-*.tgz "$OUTPUT_FILE"

echo "✓ 已生成: $OUTPUT_FILE"
```

---

### 3.5 install-plugin.sh (简化)

#### 3.5.1 变更

| 变更项 | 说明 |
|------|------|
| 移除 Python 依赖逻辑 | 调用 `install-python-deps.sh` |
| 保留构建逻辑 | 开发者从源码安装需要 |
| 保留 dry-run/verbose | 调试支持 |

#### 3.5.2 简化后流程

```bash
# 1. 检查前置条件 (node, python3, openclaw)
# 2. 构建前端 (若未构建)
# 3. 打包插件
# 4. 清理旧安装
# 5. 安装插件
# 6. 调用 install-python-deps.sh
```

---

## 四、CI/CD 配置

### 4.1 GitHub Actions 工作流

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - name: Install dependencies
        run: npm ci

      - name: Build plugin
        run: npm run pack

      - name: Create release package
        run: bash scripts/release-pack.sh

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: plugin-tgz
          path: openclaw-agent-dashboard-v*.tgz

  release:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: plugin-tgz

      - name: Get version
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/v}" >> $GITHUB_OUTPUT

      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: openclaw-agent-dashboard-v*.tgz
          generate_release_notes: true
```

---

## 五、跨平台兼容性

### 5.1 平台支持矩阵

| 平台 | 支持级别 | 说明 |
|------|----------|------|
| Linux (x64/ARM) | ✅ 完全支持 | 主要目标平台 |
| macOS (x64/ARM) | ✅ 完全支持 | 主要目标平台 |
| Windows + Git Bash | ✅ 支持 | 需要 Git for Windows |
| Windows + PowerShell | ⚠️ 部分支持 | 需提供 `install.ps1` |
| Windows + WSL | ✅ 完全支持 | 视同 Linux |

### 5.2 Windows PowerShell 脚本 (可选)

```powershell
# install.ps1
param(
  [string]$Version = "latest",
  [switch]$Verbose,
  [switch]$DryRun
)

# 检测 openclaw
if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
  Write-Error "未找到 openclaw，请先安装: npm install -g openclaw"
  exit 1
}

# 下载并安装
$DownloadUrl = "https://github.com/{owner}/{repo}/releases/download/v$Version/openclaw-agent-dashboard-v$Version.tgz"
$TempFile = Join-Path $env:TEMP "openclaw-agent-dashboard.tgz"

Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempFile
openclaw plugins install $TempFile

# Python 依赖
# ...
```

---

## 六、错误处理

### 6.1 错误码定义

| 错误码 | 说明 | 建议操作 |
|--------|------|----------|
| 1 | 前置条件不满足 | 安装缺失的依赖 |
| 2 | 下载失败 | 检查网络/代理，或手动下载 |
| 3 | 安装失败 | 查看 `VERBOSE=1` 输出 |
| 4 | Python 依赖失败 | 手动运行 `install-python-deps.sh` |
| 5 | 权限不足 | 检查目录权限 |

### 6.2 错误消息模板

```bash
log_error "下载失败: $DOWNLOAD_URL"
log_info "可能的原因:"
log_info "  1. 网络连接问题"
log_info "  2. 版本不存在: v$VERSION"
log_info "  3. GitHub 访问受限"
log_info ""
log_info "尝试:"
log_info "  1. 检查网络连接"
log_info "  2. 设置代理: export https_proxy=http://proxy:port"
log_info "  3. 手动下载: curl -LO $DOWNLOAD_URL"
log_info "  4. 指定版本: DASHBOARD_VERSION=1.0.0 bash install.sh"
```

---

## 七、测试计划

### 7.1 单元测试

| 测试项 | 测试内容 |
|--------|----------|
| `detect_os()` | Linux/macOS/Windows 正确识别 |
| `resolve_version()` | latest → 获取最新版本，指定版本 → 返回指定值 |
| `build_download_url()` | URL 格式正确 |
| `cleanup_old_installation()` | 目录被正确删除 |

### 7.2 集成测试

| 场景 | 步骤 | 预期结果 |
|------|------|----------|
| 全新安装 | 空环境 → 安装 | 插件可用 |
| 升级安装 | 旧版本 → 新版本 | 升级成功 |
| 离线安装 | 本地 tgz → 安装 | 插件可用 |
| 网络失败 | 断网 → 安装 | 明确错误提示 |
| Python 失败 | 无 pip → 安装 | 插件安装成功，提示 Python 依赖失败 |

### 7.3 平台测试

| 平台 | 测试环境 |
|------|----------|
| Linux | Ubuntu 22.04, Debian 12 |
| macOS | Intel + Apple Silicon |
| Windows | Git Bash, PowerShell |

---

## 八、实施计划

### 8.1 阶段划分

| 阶段 | 任务 | 依赖 |
|------|------|------|
| P1 | 新增 `release-pack.sh` | 无 |
| P1 | 新增 `install-python-deps.sh` | 无 |
| P1 | 简化 `install-plugin.sh` | P1 |
| P2 | 新增 `install.sh` | P1 |
| P2 | 新增 GitHub Actions | P1 |
| P3 | 新增 `install.ps1` (可选) | P2 |
| P3 | 更新 README | P2 |

### 8.2 验收标准

- [ ] `curl | bash install.sh` 可在无 Node 环境的 Linux/macOS 完成
- [ ] `DASHBOARD_VERSION=x.x.x bash install.sh` 安装指定版本
- [ ] `VERBOSE=1` 显示详细调试信息
- [ ] `DRY_RUN=1` 预览安装过程
- [ ] 升级安装正常工作
- [ ] GitHub Release 自动附带 tgz

---

## 九、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| GitHub API 限流 | 中 | 无法获取最新版本 | 使用重定向 URL 替代 API |
| GitHub Releases 不可用 | 低 | 无法下载 | 支持自定义 CDN URL |
| Python 环境问题 | 中 | 后端不可用 | 多策略安装 + 明确错误提示 |
| Windows 兼容性 | 中 | 部分用户无法使用 | 提供 Git Bash 文档 + PowerShell 脚本 |

---

## 十、附录

### A. 相关文件

| 文件 | 说明 |
|------|------|
| `docs/install-script-plan-v2.md` | 原始方案文档 |
| `scripts/install-plugin.sh` | 现有安装脚本 |
| `docs/python-environment-compatibility.md` | Python 环境兼容性说明 |

### B. 参考资料

- [openclaw plugins install 支持 .tgz 格式](验证通过)
- [npm pack 文档](https://docs.npmjs.com/cli/v10/commands/npm-pack)
- [GitHub Releases API](https://docs.github.com/en/rest/releases)

### C. 术语表

| 术语 | 说明 |
|------|------|
| tgz | tarball + gzip 压缩格式，npm pack 的输出格式 |
| PEP 668 | Python Enhancement Proposal 668，限制系统 Python 安装包 |
| venv | Python 虚拟环境，隔离依赖 |
