"""Offline checks: Python syntax, JSON, duplicate YAML keys and test discovery."""

from pathlib import Path
import ast
import json
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
UniqueLoader.add_multi_constructor("!", lambda loader, suffix, node: loader.construct_scalar(node))

if __name__ == "__main__":
    for path in ROOT.rglob("*"):
        if any(part in {".git", ".venv", "__pycache__", ".storage", "deps"} for part in path.parts):
            continue
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
        elif path.suffix == ".json":
            json.loads(path.read_text())
        elif path.suffix in {".yaml", ".yml"}:
            yaml.load(path.read_text(), Loader=UniqueLoader)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    print("Python syntax, JSON, YAML (including duplicate keys), and unit tests: OK")
