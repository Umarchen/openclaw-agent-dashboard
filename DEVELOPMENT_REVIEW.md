# OpenClaw Agent Dashboard - 开发评审报告

**评审时间**: 2026-02-26  
**评审范围**: 代码实现、环境配置、已知问题  

---

## 一、开发完成度概览

### 1.1 整体评估

| 维度 | 完成度 | 说明 |
|------|--------|------|
| **需求覆盖** | 95% | 9 个需求规格基本实现 |
| **后端实现** | 85% | 核心 API 完成，存在 2 个关键 Bug |
| **前端实现** | 90% | 工位视图、详情面板、API 状态完成 |
| **可运行性** | 60% | 环境/脚本问题导致无法启动 |

### 1.2 已实现功能

- ✅ 工位视图（主 Agent + 子 Agent）
- ✅ 状态展示（空闲/工作中/异常）
- ✅ 产出查看（点击查看详情）
- ✅ API 状态面板
- ✅ 自动刷新（10 秒）
- ✅ 需求规格、系统设计文档完整

---

## 二、发现的问题

### 2.1 🔴 阻塞性问题（导致无法运行）

#### 问题 1: setup.sh 使用 `pip` 命令

**现象**: `pip: command not found`

**原因**: 许多 Linux 系统只安装 `pip3` 或需通过 `python3 -m pip` 调用。

**修复建议**:
```bash
# 将 setup.sh 第 27 行
pip install -q -r requirements.txt

# 改为（兼容 pip/pip3）
python3 -m pip install -q -r requirements.txt
# 或
pip3 install -q -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt
```

#### 问题 2: status_calculator.py 导入路径错误

**现象**: 后端启动时会报 `ModuleNotFoundError: No module named 'status.data'`

**位置**: `src/backend/status/status_calculator.py` 第 6-8 行

**错误代码**:
```python
from .data.config_reader import get_agents_list, get_agent_config
from .data.subagent_reader import is_agent_working, get_agent_runs
from .data.session_reader import has_recent_errors, get_last_error
```

**原因**: `status` 与 `data` 是同级目录，`.data` 会解析为 `status.data`（不存在）。

**修复**:
```python
from ..data.config_reader import get_agents_list, get_agent_config
from ..data.subagent_reader import is_agent_working, get_agent_runs
from ..data.session_reader import has_recent_errors, get_last_error
```

#### 问题 3: subagent_reader.py 解析 runs.json 格式错误

**现象**: 子代理运行数据无法正确读取，状态始终为空。

**位置**: `src/backend/data/subagent_reader.py` 第 12-18 行

**原因**: OpenClaw 的 `runs.json` 实际格式为：
```json
{"version": 2, "runs": { "runId1": {...}, "runId2": {...} }}
```
而当前代码按「数组」处理：`return json.load(f)` 得到的是整个对象，后续 `for run in runs` 会遍历到 `"version"` 和 `"runs"` 字符串，而非运行记录。

**修复**:
```python
def load_subagent_runs() -> List[Dict[str, Any]]:
    """加载子代理运行记录"""
    if not SUBAGENTS_RUNS_PATH.exists():
        return []
    
    with open(SUBAGENTS_RUNS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # OpenClaw v2 格式: {"version": 2, "runs": { runId: record }}
    runs = data.get('runs', {})
    if isinstance(runs, dict):
        return list(runs.values())
    return runs if isinstance(runs, list) else []
```

### 2.2 🟡 中等问题

#### 问题 4: 主 Agent (main) 的运行记录无法获取

**原因**: `get_agent_runs` 和 `is_agent_working` 只根据 `childSessionKey` 匹配。主 Agent 派发任务时，`childSessionKey` 是 `agent:devops-agent:subagent:uuid`，不包含 `agent:main`，因此 main 永远没有运行记录。

**建议**: 对 `main` 使用 `requesterSessionKey` 判断：
```python
def _run_belongs_to_agent(run: dict, agent_id: str) -> bool:
    child = run.get('childSessionKey', '')
    requester = run.get('requesterSessionKey', '')
    if agent_id == 'main':
        return f'agent:main:' in requester or 'agent:main:main' in requester
    return f'agent:{agent_id}:' in child
```

#### 问题 5: 前端 API 请求缺少 baseURL 配置

**现象**: 开发模式下，`fetch('/api/agents')` 会请求 `http://localhost:5173/api/agents`，而 Vite 已配置 proxy 到 8000，理论上可用。需确保**先启动后端**再访问前端，否则 5173 的 proxy 会转发到未启动的 8000 导致失败。

**建议**: 在 README 中明确「必须先启动后端，再启动前端」。

#### 问题 6: workflow 接口与 workflow_state.json 结构不匹配

**现象**: `workflow_state.json` 实际结构为 `{"artifacts": {...}, "decisions": [...]}`，没有 `stages`、`currentStage` 字段。当前 API 返回空数据。

**建议**: 根据 `artifacts` 的 `status`（PENDING_REVIEW/APPROVED/REJECTED）和 `creator` 推断阶段，或扩展 workflow 的 schema。

### 2.3 🟢 轻微问题

- **拼写**: 多处 "OpenClow" 应为 "OpenClaw"
- **README 项目结构**: 写的是 `src/frontend`，实际为项目根目录的 `frontend/`
- **AgentDetailPanel 获取详情**: 当前可能只传了列表中的 agent，未调用 `GET /api/agents/:id` 获取完整输出（需确认组件实现）

---

## 三、正确的启动流程

### 3.1 修复后推荐步骤

```bash
# 1. 进入项目目录
cd /home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard

# 2. 安装后端依赖（使用 python3 -m pip）
cd src/backend
python3 -m pip install -r requirements.txt

# 3. 启动后端（保持运行）
uvicorn main:app --reload --port 8000

# 4. 新开终端，安装并启动前端
cd /home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard/frontend
npm install
npm run dev

# 5. 访问
# 看板: http://localhost:5173
# API 文档: http://localhost:8000/docs
```

### 3.2 路径说明

- **后端**: `src/backend/`（不是 `src/`）
- **前端**: `frontend/`（在项目根目录，与 `src/` 平级）
- 从 `src/backend` 到前端应使用 `cd ../../frontend`，不是 `cd frontend`

---

## 四、修复清单（按优先级）

| 优先级 | 问题 | 文件 | 操作 |
|--------|------|------|------|
| P0 | pip 命令 | setup.sh | 改为 `python3 -m pip` |
| P0 | 导入路径 | status/status_calculator.py | `.data` → `..data` |
| P0 | runs.json 解析 | data/subagent_reader.py | 支持 `{runs: {}}` 格式 |
| P1 | main Agent 运行 | data/subagent_reader.py | 增加 requesterSessionKey 判断 |
| P1 | workflow 结构 | api/workflow.py | 适配实际 workflow_state.json |
| P2 | 拼写 | 多处 | OpenClow → OpenClaw |
| P2 | README 结构 | README.md | 更正 frontend 路径说明 |

---

## 五、总结

### 开发质量

- **文档**: 需求规格、系统设计完整，结构清晰
- **架构**: 前后端分离、模块划分合理
- **实现**: 核心逻辑到位，但存在 3 个阻塞性 Bug 导致当前无法正常运行

### 建议

1. **立即修复** P0 的 3 个问题，使项目可启动
2. **补充** 后端启动时的健康检查（如 `GET /health`）
3. **验证** 修复后端到端：启动 → 访问看板 → 刷新 → 点击 Agent 详情
4. **后续** 完善 workflow 阶段推断逻辑，使流水线视图有实际数据

---

*评审完成: 2026-02-26*
