import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from astrbot.core.star.base import Star
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.star.star_tools import StarTools


def test_get_classes_falls_back_to_star_subclass_without_plugin_suffix():
    original_star_map = dict(star_map)
    star_map.clear()
    try:
        module = ModuleType("data.plugins.demo_plugin.main")
        plugin_cls = type(
            "EmbeddingAdapter",
            (Star,),
            {"__module__": module.__name__},
        )
        helper_cls = type(
            "Helper",
            (),
            {"__module__": module.__name__},
        )
        module.EmbeddingAdapter = plugin_cls
        module.Helper = helper_cls

        assert PluginManager._get_classes(module) == ["EmbeddingAdapter"]
    finally:
        star_map.clear()
        star_map.update(original_star_map)


def test_get_data_dir_falls_back_to_metadata_yaml(tmp_path: Path):
    plugin_root = tmp_path / "demo_plugin"
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        "\n".join(
            [
                'name: "demo_plugin"',
                'desc: "demo plugin"',
                'version: "1.0.0"',
                'author: "tester"',
            ]
        ),
        encoding="utf-8",
    )
    (plugin_root / "main.py").write_text(
        "def noop():\n    return None\n", encoding="utf-8"
    )

    module = ModuleType("data.plugins.demo_plugin.main")
    module.__file__ = str(plugin_root / "main.py")
    original_star_map = dict(star_map)
    star_map.clear()
    star_map[module.__name__] = StarMetadata(module_path=module.__name__)
    sys.modules[module.__name__] = module
    try:
        fake_frame = type("FakeFrame", (), {"f_back": object()})()
        with (
            patch(
                "astrbot.core.star.star_tools.inspect.currentframe",
                return_value=fake_frame,
            ),
            patch(
                "astrbot.core.star.star_tools.inspect.getmodule",
                return_value=module,
            ),
        ):
            data_dir = StarTools.get_data_dir()

        assert data_dir.name == "demo_plugin"
        assert data_dir.exists()
    finally:
        star_map.clear()
        star_map.update(original_star_map)
        sys.modules.pop(module.__name__, None)
