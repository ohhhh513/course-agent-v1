"""恢复试用代码索引之前的工作区文件；默认只预览，拒绝覆盖试用后的新改动。"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

REPO = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP = REPO / "backend/data/system-index-rollback-20261009"
if (Path(__file__).resolve().parent / "manifest.json").is_file():
    DEFAULT_BACKUP = Path(__file__).resolve().parent
    REPO = Path(json.loads((DEFAULT_BACKUP / "manifest.json").read_text(encoding="utf-8-sig"))["workspace"])


def digest(path):
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def plan_restore(backup: Path, workspace: Path):
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8-sig"))
    operations = []
    for record in manifest["files"]:
        target = (workspace / record["path"]).resolve()
        source = (backup / "files" / record["path"]).resolve()
        if not target.is_relative_to(workspace.resolve()) or not source.is_relative_to((backup / "files").resolve()):
            raise ValueError("回退路径越出指定目录")
        if record["existed"] and digest(source) != record["baseline_sha256"]:
            raise ValueError(f"回退副本损坏：{record['path']}")
        if record.get("trial_sha256") == record["baseline_sha256"]:
            continue  # 本次未改动的文件，不阻拦也不覆盖后续独立修改。
        current = digest(target)
        if current == record["baseline_sha256"]:
            continue
        if "trial_sha256" not in record or current != record["trial_sha256"]:
            raise ValueError(f"文件在试用后又有改动，拒绝覆盖：{record['path']}")
        operations.append((record, source, target))
    return operations


def restore(backup: Path, workspace: Path, apply=False):
    operations = plan_restore(backup.resolve(), workspace.resolve())
    for record, source, target in operations:
        print(("RESTORE " if record["existed"] else "REMOVE  ") + record["path"])
        if apply:
            if record["existed"]:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            else:
                target.unlink()
    return len(operations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--apply", action="store_true", help="实际恢复；默认只预览")
    args = parser.parse_args()
    # 脚本本身也在回退清单中，复制到副本里保证删除新脚本后仍能再次使用。
    count = restore(args.backup, REPO, args.apply)
    print(f"{'恢复' if args.apply else '预览'} {count} 个文件；未涉及业务数据库。")


if __name__ == "__main__":
    main()
