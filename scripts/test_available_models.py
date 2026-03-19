#!/usr/bin/env python3
"""
测试模型配置：get_all_available_models、update_agent_model 与 OpenClaw 配置格式一致性。
用法: cd 项目根目录 && python3 scripts/test_available_models.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# 添加 backend 到 path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "backend"))


def run_test_env(config: dict):
    """创建临时 openclaw.json 并设置 OPENCLAW_HOME，返回 (tmp_dir, old_home)"""
    tmp_dir = tempfile.mkdtemp()
    config_path = Path(tmp_dir) / "openclaw.json"
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    old_home = os.environ.get('OPENCLAW_HOME')
    os.environ['OPENCLAW_HOME'] = tmp_dir
    for mod in list(sys.modules.keys()):
        if 'data.config_reader' in mod or 'data.agent_config_manager' in mod:
            del sys.modules[mod]
    return tmp_dir, old_home, config_path


def run_test(name: str, config: dict) -> list:
    """用临时 openclaw.json 运行 get_all_available_models"""
    tmp_dir, old_home, _ = run_test_env(config)
    try:
        from data.agent_config_manager import get_all_available_models
        return get_all_available_models()
    finally:
        if old_home is not None:
            os.environ['OPENCLAW_HOME'] = old_home
        else:
            os.environ.pop('OPENCLAW_HOME', None)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    print("=" * 60)
    print("测试：模型列表（白名单 / providers / agents 收集）")
    print("=" * 60)

    # 场景1: agents.defaults.model + agents.list 中 agent 有 model
    config1 = {
        "agents": {
            "defaults": {
                "model": {
                    "primary": "zhipu/glm-4",
                    "fallbacks": ["zhipu/glm-4-flash"]
                }
            },
            "list": [
                {"id": "main", "name": "PM", "model": {"primary": "zhipu/glm-4.5", "fallbacks": []}},
                {"id": "analyst", "name": "BA"}
            ]
        }
    }
    # 注意：没有 models.providers

    print("\n场景1: defaults.model + list 中部分 agent 有 model")
    print("  defaults: primary=zhipu/glm-4, fallbacks=[zhipu/glm-4-flash]")
    print("  main: primary=zhipu/glm-4.5")
    print("  analyst: 无 model，继承 defaults")
    try:
        r1 = run_test("scene1", config1)
        ids = [m['id'] for m in r1]
        print(f"  结果: {ids}")
        expected = {"zhipu/glm-4.5", "zhipu/glm-4", "zhipu/glm-4-flash"}
        if set(ids) == expected:
            print("  ✓ 通过")
        else:
            print(f"  期望: {expected}, 实际: {set(ids)}")
    except Exception as e:
        print(f"  ✗ 异常: {e}")
        import traceback
        traceback.print_exc()

    # 场景2: 仅 defaults，list 中 agent 都无 model
    config2 = {
        "agents": {
            "defaults": {
                "model": {"primary": "openai/gpt-4", "fallbacks": []}
            },
            "list": [
                {"id": "main", "name": "PM"}
            ]
        }
    }
    print("\n场景2: 仅 defaults.model，agent 无 model")
    try:
        r2 = run_test("scene2", config2)
        ids = [m['id'] for m in r2]
        print(f"  结果: {ids}")
        if ids == ["openai/gpt-4"]:
            print("  ✓ 通过")
        else:
            print(f"  期望: ['openai/gpt-4'], 实际: {ids}")
    except Exception as e:
        print(f"  ✗ 异常: {e}")

    # 场景3: agents.list 为空
    config3 = {
        "agents": {
            "defaults": {"model": {"primary": "zhipu/glm-4", "fallbacks": []}},
            "list": []
        }
    }
    print("\n场景3: agents.list 为空，仅有 defaults.model")
    try:
        r3 = run_test("scene3", config3)
        ids = [m['id'] for m in r3]
        print(f"  结果: {ids}")
        if set(ids) == {"zhipu/glm-4"}:
            print("  ✓ 通过")
        else:
            print(f"  期望: ['zhipu/glm-4'], 实际: {ids}")
    except Exception as e:
        print(f"  ✗ 异常: {e}")

    # 场景3b: 有 defaults.models 但 model 中未用
    config3b = {
        "agents": {
            "defaults": {
                "model": {"primary": "zhipu/glm-4", "fallbacks": []},
                "models": {
                    "zhipu/glm-4": {"alias": "GLM-4"},
                    "zhipu/glm-4-flash": {"alias": "GLM-4 Flash"},
                    "moonshot/kimi-k2": {"alias": "Kimi K2"}
                }
            },
            "list": []
        }
    }
    print("\n场景3b: agents.defaults.models 作为白名单（有则仅显示白名单）")
    try:
        r3b = run_test("scene3b", config3b)
        ids = [m['id'] for m in r3b]
        names = [m['name'] for m in r3b]
        print(f"  结果: {ids}")
        print(f"  展示名(name): {names} (应使用 id 不用别名)")
        expected = {"zhipu/glm-4", "zhipu/glm-4-flash", "moonshot/kimi-k2"}
        if set(ids) == expected:
            # 展示名应为 id 简短形式，非 alias
            expected_names = {"glm-4", "glm-4-flash", "kimi-k2"}
            if set(names) == expected_names:
                print("  ✓ 通过（白名单 + 展示用 id）")
            else:
                print(f"  ⚠ id 正确，但 name 应为 id 形式: {expected_names}, 实际: {set(names)}")
        else:
            print(f"  期望: {sorted(expected)}, 实际: {ids}")
    except Exception as e:
        print(f"  ✗ 异常: {e}")

    # 场景3c: 有 providers + 白名单，应仅显示白名单
    config3c = {
        "models": {
            "providers": {
                "zhipu": {"models": [{"id": "glm-4"}, {"id": "glm-4-flash"}, {"id": "glm-4.5"}]},
                "openai": {"models": [{"id": "gpt-4"}]}
            }
        },
        "agents": {
            "defaults": {
                "model": {"primary": "zhipu/glm-4", "fallbacks": []},
                "models": {
                    "zhipu/glm-4": {"alias": "GLM-4"},
                    "zhipu/glm-4-flash": {"alias": "Flash"}
                }
            },
            "list": [{"id": "main", "name": "PM"}]
        }
    }
    print("\n场景3c: 有 providers + 白名单，应仅显示白名单中的模型")
    try:
        r3c = run_test("scene3c", config3c)
        ids = [m['id'] for m in r3c]
        print(f"  结果: {ids}")
        expected = {"zhipu/glm-4", "zhipu/glm-4-flash"}
        if set(ids) == expected:
            print("  ✓ 通过")
        else:
            print(f"  期望: {sorted(expected)}, 实际: {ids}")
    except Exception as e:
        print(f"  ✗ 异常: {e}")

    # 场景3e: 协作流程模型面板应仅显示 agent 配置的（不含白名单未使用的）
    config3e = {
        "agents": {
            "defaults": {
                "model": {"primary": "zhipu/glm-4", "fallbacks": []},
                "models": {
                    "zhipu/glm-4": {"alias": "GLM-4"},
                    "zhipu/glm-4-flash": {"alias": "Flash"},
                    "moonshot/kimi-k2": {"alias": "Kimi"}
                }
            },
            "list": [{"id": "main", "name": "PM"}]
        }
    }
    print("\n场景3e: 协作流程模型面板（get_models_configured_by_agents）仅 agent 配置")
    tmp_dir, old_home, _ = run_test_env(config3e)
    try:
        from data.config_reader import get_models_configured_by_agents
        configured = get_models_configured_by_agents()
        print(f"  结果: {configured}")
        if configured == ["zhipu/glm-4"]:
            print("  ✓ 通过（仅 primary，不含白名单中未用的 kimi-k2、glm-4-flash）")
        else:
            print(f"  期望: ['zhipu/glm-4'], 实际: {configured}")
    except Exception as e:
        print(f"  ✗ 异常: {e}")
    finally:
        if old_home is not None:
            os.environ['OPENCLAW_HOME'] = old_home
        else:
            os.environ.pop('OPENCLAW_HOME', None)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 场景3d: 配置保存格式（update_agent_model 写入格式与 OpenClaw 一致）
    config3d = {
        "agents": {
            "defaults": {"model": {"primary": "zhipu/glm-4", "fallbacks": []}},
            "list": [{"id": "main", "name": "PM", "model": {"primary": "zhipu/glm-4", "fallbacks": []}}]
        }
    }
    print("\n场景3d: 配置保存格式（OpenClaw agents.list[].model.primary/fallbacks）")
    tmp_dir, old_home, config_path = run_test_env(config3d)
    try:
        from data.agent_config_manager import update_agent_model, load_full_config
        res = update_agent_model("main", primary="openai/gpt-4", fallbacks=["zhipu/glm-4-flash"])
        if not res.get('success'):
            print(f"  ✗ update_agent_model 失败: {res.get('error')}")
        else:
            saved = json.loads(config_path.read_text(encoding='utf-8'))
            agent = next((a for a in saved.get('agents', {}).get('list', []) if a.get('id') == 'main'), None)
            primary = agent and agent.get('model', {}).get('primary')
            fallbacks = agent and agent.get('model', {}).get('fallbacks', [])
            if primary == "openai/gpt-4" and fallbacks == ["zhipu/glm-4-flash"]:
                print("  ✓ 通过（格式符合 OpenClaw agents.list[].model）")
            else:
                print(f"  期望 primary=openai/gpt-4 fallbacks=[zhipu/glm-4-flash]")
                print(f"  实际 primary={primary} fallbacks={fallbacks}")
    except Exception as e:
        print(f"  ✗ 异常: {e}")
    finally:
        if old_home is not None:
            os.environ['OPENCLAW_HOME'] = old_home
        else:
            os.environ.pop('OPENCLAW_HOME', None)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 场景4: 使用真实 openclaw.json（若存在）
    real_path = Path.home() / ".openclaw" / "openclaw.json"
    if real_path.exists():
        print("\n场景4: 使用真实 ~/.openclaw/openclaw.json")
        os.environ.pop('OPENCLAW_HOME', None)
        try:
            from data.agent_config_manager import get_all_available_models
            r4 = get_all_available_models()
            print(f"  结果: {len(r4)} 个模型")
            for m in r4[:5]:
                print(f"    - {m['id']} ({m['name']})")
            if len(r4) > 5:
                print(f"    ... 共 {len(r4)} 个")
        except Exception as e:
            print(f"  ✗ 异常: {e}")
    else:
        print("\n场景4: 跳过（无 ~/.openclaw/openclaw.json）")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
