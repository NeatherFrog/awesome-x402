"""One immutable-in-process version read from the shipped release manifest."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_metadata(root=ROOT):
    with (Path(root) / "RELEASE.json").open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("version"), str):
        raise ValueError("Некорректный RELEASE.json")
    return data


VERSION = release_metadata()["version"]
