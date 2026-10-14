"""实际索引与临时源码副本的热更新、缓存、权限及回退检查。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
from app.agent_st.agent.system_code_index import SystemCodeIndex
from app.agent_st.agent.system_guide import catalogue, features_for_role, lookup_guide
from system_index_rollback import plan_restore, restore


def test_refresh(root: Path):
    for role in ("student", "teacher", "admin"):
        shutil.copy2(REPO / f"{role}.html", root / f"{role}.html")
    shutil.copytree(REPO / "assets/js", root / "assets/js")
    cache = root / "cache.json"
    index = SystemCodeIndex(root, cache)
    first = index.refresh()
    assert first["changed"]
    steady = index.refresh()
    assert not steady["changed"]
    assert "intervention" not in index.pages["teacher"]
    assert not any(r["source"].endswith("/intervention.js") for r in index.records)
    assert not any(r["source"] == "assets/js/teacher/views/resource.js" for r in index.records)
    assert all(not r["source"].endswith("api.js") for r in index.records)

    source = root / "assets/js/teacher/views/structure.js"
    old = source.read_text(encoding="utf-8")
    # 增加原手册中没有的新文案，并验证接口不依赖人工维护目录。
    addition = '\nconst trial = `<button id="trialBtn">索引专属验收按钮</button>`;\n'
    assert not any("索引专属验收按钮" in str(r) for r in features_for_role("teacher"))
    source.write_text(old + addition, encoding="utf-8")
    result = index.search("teacher", "索引专属验收按钮", "structure")
    assert any("索引专属验收按钮" in r["text"] for r in result["sources"])
    assert index.stats["changed"] == ["assets/js/teacher/views/structure.js"]
    with patch("app.agent_st.agent.system_code_index._INSTANCE", index):
        tool_result = lookup_guide("teacher", query="索引专属验收按钮", view="structure")
        assert tool_result["mode"] == "code"
        assert any("索引专属验收按钮" in r["text"] for r in tool_result["sources"])
    assert all(r["role"] == "student" for r in index.search("student", "索引专属验收按钮")["sources"])
    assert not index.search("student", "trialBtn", "structure")["found"]
    stamp = source.stat()
    source.write_text((old + addition).replace("索引专属验收按钮", "源码即时刷新按钮"), encoding="utf-8")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert source.stat().st_size == stamp.st_size
    assert any("源码即时刷新按钮" in r["text"] for r in index.search("teacher", "源码即时刷新按钮", "structure")["sources"])
    assert not any("索引专属验收按钮" in r["text"] for r in index.records)
    print("PASS 修改与同大小/保留 mtime 保存：下一次查询读取新内容")

    added = root / "assets/js/teacher/views/index-trial.js"
    added.write_text('Router.register("structure", { mount() { return "新增文件热更新凭据"; } });', encoding="utf-8")
    html = root / "teacher.html"
    original_html = html.read_text(encoding="utf-8")
    # 未加载的文件不应误判为已上线功能。
    index.refresh()
    assert not any("index-trial.js" in r["source"] for r in index.records)
    html.write_text(original_html + '<script src="assets/js/teacher/views/index-trial.js"></script>', encoding="utf-8")
    assert any("新增文件热更新凭据" in r["text"] for r in index.search("teacher", "新增文件热更新凭据")["sources"])
    added.unlink()
    index.refresh()
    assert "assets/js/teacher/views/index-trial.js" in index.stats["removed"]
    assert not any("index-trial.js" in r["source"] for r in index.records)
    added.write_text('Router.register("structure", { mount() { return "重新加载凭据"; } });', encoding="utf-8")
    index.refresh()
    assert any("index-trial.js" in r["source"] for r in index.records)
    html.write_text(original_html, encoding="utf-8")
    index.refresh()
    assert added.is_file() and not any("index-trial.js" in r["source"] for r in index.records)
    html.write_text(original_html + '<script src="assets/js/teacher/../student/views/resource.js"></script>', encoding="utf-8")
    index.refresh()
    assert not any(r["role"] == "teacher" and r["source"].startswith("assets/js/teacher/../student") for r in index.records)
    html.write_text(original_html, encoding="utf-8")
    print("PASS 新文件加载、未加载文件排除、删除文件、移除 HTML 引用及跨角色路径拒绝")
    # 删除导航入口后，后端建议工具不得继续提供该入口。
    html.write_text(original_html.replace('data-view="structure"', 'data-hidden-view="structure"'), encoding="utf-8")
    from app.agent_st.agent.context import ToolContext
    from app.agent_st.agent.registry import execute
    from app.agent_st.agent.tools import analytics  # noqa: F401
    with patch("app.agent_st.agent.system_code_index._INSTANCE", index):
        ctx = ToolContext(store=None, flow_id="explain", extra={"role": "teacher"})
        assert "error" in execute("suggest_action", {"kind": "navigate", "view": "structure", "label": "打开页面"}, ctx)
        assert not ctx.turn.get("actions")
    html.write_text(original_html, encoding="utf-8")
    source.write_text(old, encoding="utf-8")
    index.refresh()
    assert not any("源码即时刷新按钮" in r["text"] for r in index.records)

    reloaded = SystemCodeIndex(root, cache)
    assert not reloaded.refresh()["changed"]
    assert reloaded.search("teacher", "stNewCh", "structure")["found"]
    cache.write_text("invalid cache", encoding="utf-8")
    with patch("app.agent_st.agent.system_code_index.LOG.warning") as warning:
        assert SystemCodeIndex(root, cache).search("teacher", "stNewCh", "structure")["found"]
        assert warning.called
    cached = json.loads(cache.read_text(encoding="utf-8"))
    cached["files"]["assets/js/teacher/views/structure.js"]["text"] = "伪造缓存正文"
    cache.write_text(json.dumps(cached), encoding="utf-8")
    recovered = SystemCodeIndex(root, cache)
    assert recovered.search("teacher", "stNewCh", "structure")["found"]
    assert not any("伪造缓存正文" in r["text"] for r in recovered.records)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: index.search("teacher", "stNewCh", "structure"), range(12)))
    assert all(r["found"] for r in results)
    print("PASS 缓存重载、损坏重建和并发读取")
    with patch.dict(os.environ, {"SYSTEM_GUIDE_MODE": "manual"}):
        fallback = lookup_guide("teacher", feature_id="teacher.structure.chapter.edit")
        assert fallback["found"] and "sources" not in fallback
    with patch("app.agent_st.agent.system_code_index.get_code_index", side_effect=OSError("source unavailable")), \
            patch("app.agent_st.agent.system_guide.LOG.warning"):
        fallback = lookup_guide("teacher", feature_id="teacher.structure.chapter.edit")
        assert fallback["found"] and fallback["mode"] == "manual_fallback" and fallback["warning"]
    print("PASS 导航移除即时拒绝、手册开关和索引读取失败回退")

    timings = []
    for _ in range(20):
        started = time.perf_counter()
        index.search("teacher", "修改章节名称", "structure")
        timings.append((time.perf_counter() - started) * 1000)
    print(f"索引：{first['files']} 文件 / {first['chunks']} 片段；首次构建 {first['refresh_ms']:.2f} ms；"
          f"复用查询中位数 {statistics.median(timings):.2f} ms / 最大 {max(timings):.2f} ms")


def test_rollback(root: Path):
    root.mkdir()
    backup = REPO / "backend/data/system-index-rollback-20261009"
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8-sig"))
    for record in manifest["files"]:
        live = REPO / record["path"]
        if live.is_file():
            target = root / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live, target)
    operations = plan_restore(backup, root)
    assert operations, "试用文件必须与基线有差异"
    drift_target = operations[0][2]
    original = drift_target.read_bytes()
    drift_target.write_bytes(original + b"\nuser edits after trial\n")
    try:
        plan_restore(backup, root)
    except ValueError:
        pass
    else:
        raise AssertionError("回退必须拒绝覆盖后续新改动")
    drift_target.write_bytes(original)
    restore(backup, root, apply=True)
    for record in manifest["files"]:
        path = root / record["path"]
        assert (sha256(path.read_bytes()).hexdigest() if path.is_file() else None) == record["baseline_sha256"]
    assert not plan_restore(backup, root)
    print("PASS 试用前基线逐文件 SHA256 恢复与幂等回退；后续用户改动保护")


def main():
    index = SystemCodeIndex(REPO)
    index.refresh()
    for role in ("student", "teacher", "admin"):
        assert set(index.pages[role]) == set(catalogue()["roles"][role]["pages"])
    # 源码绑定 id 并未写进手册标题/步骤，仍可查询到具体原文。
    for role, query, view in [("teacher", "eqAddOpt", "question"), ("student", "rsContinue", "practice"),
                               ("admin", "bdConfirm", "users")]:
        result = lookup_guide(role, query=query, view=view)
        assert result["mode"] == "code"
        assert any(query in r["text"] for r in result["sources"])
    print("PASS 三端查询实际源码绑定；新细节不依赖手册编号")
    with tempfile.TemporaryDirectory(prefix="system-index-check-") as directory:
        fixture = Path(directory) / "source"
        fixture.mkdir()
        test_refresh(fixture)
        # 新克隆没有本地回退副本时，索引测试仍可运行。
        if (REPO / "backend/data/system-index-rollback-20261009/manifest.json").is_file():
            test_rollback(Path(directory) / "rollback")
    print("全部通过；真实源码和数据库未被测试修改。")


if __name__ == "__main__":
    main()
