import sys
import tempfile
import types
import unittest
from pathlib import Path


class _FakeRoutes:
    def get(self, _path):
        def deco(fn):
            return fn
        return deco

    def post(self, _path):
        def deco(fn):
            return fn
        return deco


class _FakePromptServerClass:
    instance = types.SimpleNamespace(routes=_FakeRoutes(), send_sync=lambda *_args, **_kwargs: None)


def _load_nodes_module():
    fake_web = types.SimpleNamespace(
        Response=lambda *args, **kwargs: types.SimpleNamespace(args=args, kwargs=kwargs),
        FileResponse=lambda *args, **kwargs: types.SimpleNamespace(args=args, kwargs=kwargs, content_type=None),
        json_response=lambda payload: payload,
    )
    fake_aiohttp = types.ModuleType("aiohttp")
    fake_aiohttp.web = fake_web
    sys.modules["aiohttp"] = fake_aiohttp

    fake_server = types.ModuleType("server")
    fake_server.PromptServer = _FakePromptServerClass
    sys.modules["server"] = fake_server

    import importlib

    if "nodes" in sys.modules:
        del sys.modules["nodes"]
    return importlib.import_module("nodes")


class TestPruneCleanup(unittest.TestCase):
    def test_prune_removes_full_and_thumb_files(self):
        nodes = _load_nodes_module()

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            full_old = temp_dir / "old.png"
            thumb_old = temp_dir / "old.webp"
            full_new = temp_dir / "new.png"
            thumb_new = temp_dir / "new.webp"

            for p in (full_old, thumb_old, full_new, thumb_new):
                p.write_bytes(b"x")

            state = {
                "entries": [
                    {"id": "old", "full_path": str(full_old), "thumb_path": str(thumb_old)},
                    {"id": "new", "full_path": str(full_new), "thumb_path": str(thumb_new)},
                ]
            }

            nodes._prune_entries("node-1", state, 1)

            self.assertEqual(len(state["entries"]), 1)
            self.assertEqual(state["entries"][0]["id"], "new")
            self.assertFalse(full_old.exists())
            self.assertFalse(thumb_old.exists())
            self.assertTrue(full_new.exists())
            self.assertTrue(thumb_new.exists())


if __name__ == "__main__":
    unittest.main()
