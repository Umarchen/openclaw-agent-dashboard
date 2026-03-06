# 安装脚本重构计划

> 创建日期: 2026-03-06
> 完成日期: 2026-03-06
> 状态: ✅ 已完成

---

## 一、重构目标

1. **消除代码重复** - 公共函数提取到独立文件 ✅
2. **明确职责边界** - 每个脚本只负责一件事 ✅
3. **保持向后兼容** - 不破坏现有功能 ✅
4. **简化维护** - 单一修改点 ✅

---

## 二、保留的修改

### 2.1 plugin/index.js (保留) ✅

```diff
- const pythonCmd = process.env.PYTHON_CMD || 'python3';
+ // 优先使用插件 venv 的 Python（安装时 venv 优先，避免 PEP 668）
+ const venvPythonUnix = path.join(dashboardDir, '.venv', 'bin', 'python');
+ const venvPythonWin = path.join(dashboardDir, '.venv', 'Scripts', 'python.exe');
+ let pythonCmd =
+   process.env.PYTHON_CMD ||
+   (fs.existsSync(venvPythonUnix) ? venvPythonUnix : null) ||
+   (fs.existsSync(venvPythonWin) ? venvPythonWin : null) ||
+   'python3';
```

**原因**: 运行时与安装脚本保持一致的 venv 优先策略

---

## 三、重构步骤

### Phase 1: 创建公共库 [✅]

- [x] **1.1** 创建 `scripts/lib/common.sh`
  - 日志函数: log_info, log_ok, log_warn, log_error
  - run_silent 函数
  - resolve_openclaw_config_dir 函数
  - parse_json_version 函数
  - detect_os / validate_os 函数
  - download_file 函数

- [x] **1.2** 测试公共库
  ```bash
  bash -n scripts/lib/common.sh  # ✓ 通过
  ```

### Phase 2: 重构 install-plugin.sh [✅]

- [x] **2.1** 引入公共库
- [x] **2.2** 删除重复的函数定义
- [x] **2.3** 测试
  ```bash
  bash -n scripts/install-plugin.sh  # ✓ 通过
  DRY_RUN=1 bash scripts/install-plugin.sh  # ✓ 通过
  ```

### Phase 3: 重构 install.sh [✅]

- [x] **3.1** 统一函数定义（内联方式，curl | bash 兼容）
- [x] **3.2** 删除重复的函数定义
- [x] **3.3** 简化 Python 依赖安装逻辑（内联函数）
- [x] **3.4** 测试
  ```bash
  bash -n scripts/install.sh  # ✓ 通过
  DRY_RUN=1 bash scripts/install.sh  # ✓ 通过
  ```

### Phase 4: 统一 release-pack.sh [✅]

- [x] **4.1** 引入公共库
- [x] **4.2** 删除重复的版本解析逻辑
- [x] **4.3** 测试
  ```bash
  bash -n scripts/release-pack.sh  # ✓ 通过
  ```

### Phase 5: 全量测试 [✅]

- [x] **5.1** 语法检查 - 全部通过
- [x] **5.2** DRY_RUN 测试 - 全部通过
- [x] **5.3** 本地安装测试 - 通过
- [x] **5.4** 验证安装结果 - 插件已安装

### Phase 6: 文档整理 [✅]

- [x] **6.1** 删除过时文档 `docs/specs/dev-plan-install-system.md`
- [x] **6.2** 更新本文档状态为完成

### Phase 7: 提交 [ ]

待用户确认后执行

---

## 四、文件变更清单

### 4.1 新增文件

| 文件 | 说明 |
|------|------|
| `scripts/lib/common.sh` | 公共函数库 |
| `docs/refactor/install-refactor-plan.md` | 本文档 |

### 4.2 修改文件

| 文件 | 变更说明 |
|------|----------|
| `scripts/install-plugin.sh` | 引入公共库，删除重复代码 |
| `scripts/install.sh` | 统一函数定义 |
| `scripts/release-pack.sh` | 引入公共库 |
| `plugin/index.js` | venv Python 优先 |

### 4.3 删除文件

| 文件 | 原因 |
|------|------|
| `docs/specs/dev-plan-install-system.md` | 任务已完成 |

---

## 五、测试记录

| 测试项 | 命令 | 结果 | 日期 |
|--------|------|------|------|
| 语法检查 | `bash -n scripts/lib/common.sh` | ✅ 通过 | 2026-03-06 |
| 语法检查 | `bash -n scripts/install-plugin.sh` | ✅ 通过 | 2026-03-06 |
| 语法检查 | `bash -n scripts/install.sh` | ✅ 通过 | 2026-03-06 |
| 语法检查 | `bash -n scripts/release-pack.sh` | ✅ 通过 | 2026-03-06 |
| DRY_RUN | `DRY_RUN=1 bash scripts/install-plugin.sh` | ✅ 通过 | 2026-03-06 |
| DRY_RUN | `DRY_RUN=1 bash scripts/install.sh` | ✅ 通过 | 2026-03-06 |
| 本地安装 | `npm run deploy` | ✅ 通过 | 2026-03-06 |

---

## 六、进度追踪

- [x] Phase 1: 创建公共库
- [x] Phase 2: 重构 install-plugin.sh
- [x] Phase 3: 重构 install.sh
- [x] Phase 4: 统一 release-pack.sh
- [x] Phase 5: 全量测试
- [x] Phase 6: 文档整理
- [ ] Phase 7: 提交

**当前进度**: 6/7

---

## 七、提交命令

确认后执行：

```bash
git add scripts/lib/common.sh
git add scripts/install.sh
git add scripts/install-plugin.sh
git add scripts/release-pack.sh
git add plugin/index.js
git add docs/refactor/install-refactor-plan.md
git add README.md

git commit -m "refactor: 提取公共库，消除安装脚本重复代码

- 新增 scripts/lib/common.sh 公共函数库
- 重构 install-plugin.sh 使用公共库
- 重构 install.sh 统一函数定义
- 重构 release-pack.sh 使用公共库
- plugin/index.js 优先使用 venv Python
- 删除过时的开发计划文档"
```
