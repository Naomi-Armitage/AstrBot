import builtins
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import yaml

from astrbot.core.star.star_manager import PluginManager

TEST_PLUGIN_NAME = "helloworld"
TEST_PLUGIN_REPO = "https://github.com/AstrBotDevs/astrbot_plugin_helloworld"
TEST_PLUGIN_DIR = "helloworld"


def _write_local_test_plugin(plugin_path: Path, repo_url: str) -> None:
    plugin_path.mkdir(parents=True, exist_ok=True)
    metadata = {
        "name": TEST_PLUGIN_NAME,
        "repo": repo_url,
        "version": "1.0.0",
        "author": "AstrBot Team",
        "desc": "Local test plugin",
    }
    with open(plugin_path / "metadata.yaml", "w", encoding="utf-8") as f:
        yaml.dump(metadata, f)
    with open(plugin_path / "main.py", "w", encoding="utf-8") as f:
        f.write("from astrbot.api.star import Star, Context, StarManager\n")
        f.write("@StarManager.register\n")
        f.write("class HelloWorld(Star):\n")
        f.write("    def __init__(self, context: Context): ...\n")


def _clear_module_cache() -> None:
    import sys

    to_delete = [name for name in sys.modules if name.startswith("data.plugins.helloworld")]
    for module_name in to_delete:
        del sys.modules[module_name]


@pytest.fixture
def plugin_manager_pm(tmp_path, monkeypatch):
    _clear_module_cache()

    plugin_dir = tmp_path / "astrbot_root" / "data" / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    class MockContext:
        def __init__(self):
            self.stars = []

        def get_all_stars(self):
            return self.stars

        def get_registered_star(self, name):
            for star in self.stars:
                if star.root_dir_name == name or star.name == name:
                    return star
            return None

    pm = PluginManager(cast(Any, MockContext()), cast(Any, {}))
    monkeypatch.setattr(pm, "plugin_store_path", str(plugin_dir))
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.get_astrbot_plugin_path",
        lambda: str(plugin_dir),
    )
    return pm


@pytest.fixture
def local_updator(plugin_manager_pm):
    plugin_path = Path(plugin_manager_pm.plugin_store_path) / TEST_PLUGIN_DIR
    _write_local_test_plugin(plugin_path, TEST_PLUGIN_REPO)
    return plugin_path


@pytest.mark.asyncio
async def test_import_plugin_with_dependency_recovery_skips_internal_missing_module_recovery(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    target_module = "data.plugins.helloworld.main"
    missing_module = "data.plugins.helloworld.private_chat.private_chat_utils._session_guard"
    original_import = builtins.__import__
    events = []

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == target_module:
            raise ModuleNotFoundError(
                f"No module named '{missing_module}'",
                name=missing_module,
            )
        return original_import(name, globals, locals, fromlist, level)

    async def mock_check_plugin_deps(*, target_plugin=None):
        events.append(("deps", target_plugin))

    # 让恢复模式与"示例依赖(networkx)是否恰好已装"无关：plan=None 表示
    # 无需安装 -> RECOVER_ON_FAILURE（不预加载），从而测试只验证恢复逻辑本身。
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.plan_missing_requirements_install",
        lambda requirements_path: None,
    )
    monkeypatch.setattr("builtins.__import__", mock_import)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        plugin_manager_pm,
        "_check_plugin_dept_update",
        mock_check_plugin_deps,
    )

    with pytest.raises(ModuleNotFoundError) as exc_info:
        await plugin_manager_pm._import_plugin_with_dependency_recovery(
            path=target_module,
            module_str="main",
            root_dir_name=TEST_PLUGIN_DIR,
            requirements_path=str(requirements_path),
        )

    assert exc_info.value.name == missing_module
    assert events == []


@pytest.mark.asyncio
async def test_import_plugin_with_dependency_recovery_prefers_installed_external_dependencies(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    target_module = "data.plugins.helloworld.main"
    resolved_module = ModuleType("helloworld_main")
    original_import = builtins.__import__
    attempts = {"count": 0}
    events = []

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == target_module:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ModuleNotFoundError(
                    "No module named 'networkx'",
                    name="networkx",
                )
            return resolved_module
        return original_import(name, globals, locals, fromlist, level)

    async def mock_check_plugin_deps(*, target_plugin=None):
        events.append(("deps", target_plugin))

    # 让恢复模式与"示例依赖(networkx)是否恰好已装"无关：plan=None 表示
    # 无需安装 -> RECOVER_ON_FAILURE（不预加载），从而测试只验证恢复逻辑本身。
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.plan_missing_requirements_install",
        lambda requirements_path: None,
    )
    monkeypatch.setattr("builtins.__import__", mock_import)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        plugin_manager_pm,
        "_check_plugin_dept_update",
        mock_check_plugin_deps,
    )

    module = await plugin_manager_pm._import_plugin_with_dependency_recovery(
        path=target_module,
        module_str="main",
        root_dir_name=TEST_PLUGIN_DIR,
        requirements_path=str(requirements_path),
    )

    assert module is resolved_module
    assert events == [("prefer", str(requirements_path))]
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_import_plugin_with_dependency_recovery_does_not_treat_similar_prefix_as_internal(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    target_module = "data.plugins.helloworld.main"
    resolved_module = ModuleType("helloworld_main")
    original_import = builtins.__import__
    attempts = {"count": 0}
    events = []

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == target_module:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ModuleNotFoundError(
                    "No module named 'data.plugins.helloworld_extra'",
                    name="data.plugins.helloworld_extra",
                )
            return resolved_module
        return original_import(name, globals, locals, fromlist, level)

    async def mock_check_plugin_deps(*, target_plugin=None):
        events.append(("deps", target_plugin))

    # 让恢复模式与"示例依赖(networkx)是否恰好已装"无关：plan=None 表示
    # 无需安装 -> RECOVER_ON_FAILURE（不预加载），从而测试只验证恢复逻辑本身。
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.plan_missing_requirements_install",
        lambda requirements_path: None,
    )
    monkeypatch.setattr("builtins.__import__", mock_import)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        plugin_manager_pm,
        "_check_plugin_dept_update",
        mock_check_plugin_deps,
    )

    module = await plugin_manager_pm._import_plugin_with_dependency_recovery(
        path=target_module,
        module_str="main",
        root_dir_name=TEST_PLUGIN_DIR,
        requirements_path=str(requirements_path),
    )

    assert module is resolved_module
    assert events == [("prefer", str(requirements_path))]
    assert attempts["count"] == 2
