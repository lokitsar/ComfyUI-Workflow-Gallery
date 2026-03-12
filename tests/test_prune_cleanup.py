import asyncio
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


class _FakeRequest:
    def __init__(self, node_id):
        self.match_info = {"node_id": node_id}


class _FakeTensor:
    def __init__(self, arr):
        self._arr = arr

    def cpu(self):
        return self

    def numpy(self):
        return self._arr


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
    def test_prune_removes_full_and_thumb_files_and_index(self):
        nodes = _load_nodes_module()

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            full_old = temp_dir / "old.png"
            thumb_old = temp_dir / "old.webp"
            full_new = temp_dir / "new.png"
            thumb_new = temp_dir / "new.webp"

            for p in (full_old, thumb_old, full_new, thumb_new):
                p.write_bytes(b"x")

            old_entry = {"id": "old", "full_path": str(full_old), "thumb_path": str(thumb_old)}
            new_entry = {"id": "new", "full_path": str(full_new), "thumb_path": str(thumb_new)}
            state = {"entries": [old_entry, new_entry]}
            nodes.ENTRY_INDEX["old"] = old_entry
            nodes.ENTRY_INDEX["new"] = new_entry

            nodes._prune_entries("node-1", state, 1)

            self.assertEqual(len(state["entries"]), 1)
            self.assertEqual(state["entries"][0]["id"], "new")
            self.assertFalse(full_old.exists())
            self.assertFalse(thumb_old.exists())
            self.assertTrue(full_new.exists())
            self.assertTrue(thumb_new.exists())
            self.assertIsNone(nodes._find_entry("old"))
            self.assertIs(nodes._find_entry("new"), new_entry)


    def test_legacy_output_directory_maps_to_comfy_output(self):
        nodes = _load_nodes_module()

        legacy_path = str(nodes.PACKAGE_DIR / "gallery_output")
        normalized = nodes._normalize_output_dir(legacy_path)

        self.assertEqual(normalized, nodes.DEFAULT_SAVE_DIR)

    def test_clear_removes_entries_from_index(self):
        nodes = _load_nodes_module()

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            full_path = temp_dir / "one.png"
            thumb_path = temp_dir / "one.webp"
            full_path.write_bytes(b"x")
            thumb_path.write_bytes(b"x")

            entry = {"id": "entry-1", "full_path": str(full_path), "thumb_path": str(thumb_path)}
            nodes.GALLERY_STATE["node-1"] = {
                "entries": [entry],
                "max_images": 10,
                "output_directory": str(temp_dir),
            }
            nodes.ENTRY_INDEX[entry["id"]] = entry

            result = asyncio.run(nodes.workflow_gallery_clear(_FakeRequest("node-1")))

            self.assertEqual(result["ok"], True)
            self.assertEqual(nodes.GALLERY_STATE["node-1"]["entries"], [])
            self.assertIsNone(nodes._find_entry("entry-1"))
            self.assertFalse(full_path.exists())
            self.assertFalse(thumb_path.exists())


    def test_collect_save_to_disk_true_writes_to_selected_output_dir(self):
        nodes = _load_nodes_module()

        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td) / "out"
            image = _FakeTensor(np.ones((8, 8, 3), dtype=np.float32))

            gallery = nodes.WorkflowGallery()
            gallery.collect([image], save_to_disk=True, output_directory=str(output_dir), unique_id="node-save-true")

            entries = nodes.GALLERY_STATE["node-save-true"]["entries"]
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertTrue(Path(entry["full_path"]).exists())
            self.assertTrue(str(Path(entry["full_path"]).parent).startswith(str(output_dir.resolve())))

    def test_collect_save_to_disk_false_writes_to_cache_dir(self):
        nodes = _load_nodes_module()

        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td) / "out"
            image = _FakeTensor(np.ones((8, 8, 3), dtype=np.float32))

            gallery = nodes.WorkflowGallery()
            gallery.collect([image], save_to_disk=False, output_directory=str(output_dir), unique_id="node-save-false")

            entries = nodes.GALLERY_STATE["node-save-false"]["entries"]
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            full_path = Path(entry["full_path"]).resolve()
            self.assertTrue(full_path.exists())
            self.assertEqual(full_path.parent.name, "unsaved_cache")
            self.assertTrue(str(full_path).startswith(str(nodes.CACHE_BASE_DIR.resolve())))
            self.assertEqual(nodes.GALLERY_STATE["node-save-false"]["save_to_disk"], False)



if __name__ == "__main__":
    unittest.main()
