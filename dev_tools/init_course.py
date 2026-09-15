"""
开发用：通过 HTTP API 批量初始化课程（章 / KP / 资源 / 可选题与图谱边）。

隔离约定：
  - 仅本目录脚本；不被 backend/app 启动链路 import
  - 只访问已运行的后端（默认 127.0.0.1:8000），不用 TestClient
  - 不修改演示课默认数据，除非配置显式 useCourseId

用法见 dev_tools/README.md
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token = ""
        self.course_id = ""
        self._op = _opener()

    def hdrs(self, extra: dict | None = None) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.course_id:
            h["X-Course-Id"] = self.course_id
        if extra:
            h.update(extra)
        return h

    def req(self, method: str, path: str, body=None, headers=None, raw=False):
        url = self.base + path
        data = None
        ctype = None
        if body is not None and not raw:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            ctype = "application/json"
        elif raw and body is not None:
            data = body
        r = urllib.request.Request(url, data=data, method=method)
        for k, v in (headers or self.hdrs()).items():
            if k.lower() == "content-type" and ctype and not raw:
                continue
            if k.lower() == "content-type" and raw:
                continue
            r.add_header(k, v)
        if ctype and not raw:
            r.add_header("Content-Type", ctype)
        try:
            with self._op.open(r, timeout=120) as resp:
                raw_txt = resp.read()
                if raw:
                    return resp.status, raw_txt
                return resp.status, json.loads(raw_txt.decode("utf-8") or "null")
        except urllib.error.HTTPError as e:
            raw_txt = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(raw_txt)
            except Exception:
                return e.code, {"code": e.code, "message": raw_txt[:300]}

    def ok_data(self, method, path, body=None, headers=None):
        st, j = self.req(method, path, body=body, headers=headers)
        if st != 200 or (isinstance(j, dict) and j.get("code") not in (0, None) and j.get("data") is None and j.get("code") != 0):
            msg = j.get("message") or j.get("detail") or str(j)[:200] if isinstance(j, dict) else str(j)
            raise RuntimeError(f"{method} {path} -> {st}: {msg}")
        if isinstance(j, dict) and "code" in j and j["code"] != 0:
            raise RuntimeError(f"{method} {path}: {j.get('message') or j.get('detail')}")
        return j.get("data") if isinstance(j, dict) else j


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("teacher", "course", "chapters"):
        if key not in cfg:
            raise SystemExit(f"配置缺少必填段: {key}")
    return cfg


def resolve_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = ROOT / p
    return path


def multipart(fields: dict, file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----devtools" + uuid_hex()
    lines: list[bytes] = []
    for k, v in fields.items():
        if v is None:
            continue
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        lines.append(str(v).encode("utf-8"))
        lines.append(b"\r\n")
    lines.append(f"--{boundary}\r\n".encode())
    filename = file_path.name
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    lines.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
    )
    lines.append(f"Content-Type: {mime}\r\n\r\n".encode())
    lines.append(file_path.read_bytes())
    lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    return b"".join(lines), boundary


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex


def upload_resource(api: Api, item: dict, kp_name_to_id: dict, ch_name_to_id: dict) -> dict:
    fpath = resolve_path(item["file"])
    if not fpath.is_file():
        raise FileNotFoundError(f"资源文件不存在: {fpath}")
    chapter = item.get("chapter") or ""
    ch_id = ch_name_to_id.get(chapter, "")
    kp_names = item.get("kps") or []
    kp_ids = [kp_name_to_id[n] for n in kp_names if n in kp_name_to_id]
    primary = kp_ids[0] if kp_ids else ""
    primary_name = kp_names[0] if kp_names else ""
    fields = {
        "title": item.get("title") or fpath.stem,
        "chapterId": ch_id,
        "chapter": chapter,
        "kpIds": json.dumps(kp_ids, ensure_ascii=False),
        "kp_id": primary,
        "kp": primary_name,
        "category": "knowledge" if kp_ids else "other",
    }
    body, boundary = multipart(fields, "file", fpath)
    r = urllib.request.Request(
        api.base + "/api/v1/teacher/resources/upload",
        data=body,
        method="POST",
    )
    r.add_header("Authorization", f"Bearer {api.token}")
    r.add_header("X-Course-Id", api.course_id)
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with api._op.open(r, timeout=180) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        j = {"code": e.code, "message": e.read().decode("utf-8", "replace")[:300]}
    if not isinstance(j, dict) or j.get("code") != 0:
        raise RuntimeError(f"上传失败 {fpath.name}: {j}")
    return j.get("data") or {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="通过 API 初始化课程（开发用）")
    ap.add_argument("--config", default=str(Path(__file__).parent / "sample_config.json"))
    ap.add_argument("--base", default=None, help="覆盖 baseUrl，如 http://127.0.0.1:8000")
    ap.add_argument("--skip-uploads", action="store_true", help="不上传资源文件")
    args = ap.parse_args(argv)

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"[error] 配置不存在: {cfg_path}")
        return 1
    cfg = load_config(cfg_path)
    base = args.base or cfg.get("baseUrl") or "http://127.0.0.1:8000"
    api = Api(base)
    print(f"[init] base={base}")
    print("[init] 本脚本仅开发用，不会随服务自动执行。")

    # 1) 登录教师
    t = cfg["teacher"]
    st, j = api.req(
        "POST",
        "/api/v1/auth/login",
        body={"username": t["username"], "password": t["password"]},
        headers={"Content-Type": "application/json"},
    )
    if st != 200 or j.get("code") != 0:
        print(f"[error] 教师登录失败: {j}")
        return 1
    api.token = j["data"]["token"]
    print(f"[init] 教师登录成功: {t['username']}")

    # 2) 课程
    cmeta = cfg["course"]
    invite = ""
    if cmeta.get("useCourseId"):
        api.course_id = cmeta["useCourseId"]
        # 校验成员
        st, j = api.req("GET", "/api/v1/teacher/structure", headers=api.hdrs())
        if st != 200 or j.get("code") != 0:
            print(f"[error] 无法访问课程 {api.course_id}（未加入或课号错误）: {j.get('message') or j.get('detail')}")
            return 1
        print(f"[init] 使用已有课程: {api.course_id}")
    else:
        st, j = api.req(
            "POST",
            "/api/v1/teacher/courses",
            body={"name": cmeta["name"], "term": cmeta.get("term") or "", "code": cmeta.get("code") or ""},
            headers={"Authorization": f"Bearer {api.token}"},
        )
        if st != 200 or j.get("code") != 0:
            print(f"[error] 建课失败: {j}")
            return 1
        api.course_id = j["data"]["courseId"]
        invite = j["data"].get("inviteCode") or ""
        print(f"[init] 新建课程 courseId={api.course_id} inviteCode={invite}")

    H = api.hdrs()

    # 3) 章 + KP
    ch_name_to_id: dict[str, str] = {}
    kp_name_to_id: dict[str, str] = {}
    n_ch = n_kp = 0
    for ch in cfg.get("chapters") or []:
        name = (ch.get("name") or "").strip()
        if not name:
            continue
        st, j = api.req(
            "POST",
            "/api/v1/teacher/structure/chapters",
            body={"name": name, "hours": int(ch.get("hours") or 0)},
            headers=H,
        )
        if st != 200 or j.get("code") != 0:
            # 可能已存在：从 structure 回查
            print(f"[warn] 建章失败或已存在: {name} -> {j.get('message') or j.get('detail')}")
        else:
            ch_name_to_id[name] = j["data"]["id"]
            n_ch += 1
        for kp_name in ch.get("kps") or []:
            st, j = api.req(
                "POST",
                "/api/v1/teacher/structure/kps",
                body={"name": kp_name, "chapterId": ch_name_to_id.get(name, ""), "hours": int(ch.get("kpHours") or 0), "isKey": bool(ch.get("isKey"))},
                headers=H,
            )
            if st != 200 or j.get("code") != 0:
                print(f"[warn] 建 KP 失败或已存在: {kp_name} -> {j.get('message') or j.get('detail')}")
            else:
                kp_name_to_id[kp_name] = j["data"]["id"]
                n_kp += 1

    # 刷新 structure，回填可能已存在的 id
    st, j = api.req("GET", "/api/v1/teacher/structure", headers=H)
    if st == 200 and j.get("code") == 0:
        data = j["data"]
        for c in data.get("chapterOptions") or []:
            ch_name_to_id.setdefault(c["name"], c["id"])
        for k in data.get("kpOptions") or []:
            kp_name_to_id.setdefault(k["name"], k["id"])
        # 章下 KP 也补全
        for c in data.get("chapters") or []:
            ch_name_to_id.setdefault(c.get("name") or "", c.get("id") or "")
            for k in c.get("kps") or []:
                kp_name_to_id.setdefault(k.get("name") or "", k.get("id") or "")

    print(f"[init] 章节新建 {n_ch}，KP 新建 {n_kp}；目录映射章 {len(ch_name_to_id)} / KP {len(kp_name_to_id)}")

    # 4) 上传资源
    n_up = n_fail = 0
    if not args.skip_uploads:
        for item in cfg.get("resources") or []:
            try:
                up = upload_resource(api, item, kp_name_to_id, ch_name_to_id)
                print(f"  [upload] OK {item.get('title') or item['file']} -> {up.get('resId')}")
                n_up += 1
            except Exception as e:
                n_fail += 1
                print(f"  [upload] FAIL {item.get('file')}: {e}")
    else:
        print("[init] 已跳过资源上传")

    # 5) 可选：题目批量导入
    n_q = 0
    qf = cfg.get("questionsFile")
    if qf:
        qp = resolve_path(qf)
        if not qp.is_file():
            print(f"[warn] questionsFile 不存在: {qp}")
        else:
            qlist = json.loads(qp.read_text(encoding="utf-8"))
            if not isinstance(qlist, list):
                print("[warn] questionsFile 必须是 JSON 数组")
            else:
                # 将 kpNames 解析为当前课的 kp_id，再走标准导入契约
                resolved = []
                missing_kp = 0
                for q in qlist:
                    q2 = dict(q)
                    names = q2.pop("kpNames", None) or q2.pop("kp_names", None) or []
                    ids = [kp_name_to_id[n] for n in names if n in kp_name_to_id]
                    if names and not ids:
                        missing_kp += 1
                    if ids:
                        q2["kp_ids"] = ids
                        q2["kp_id"] = ids[0]
                    # 章名 → chapterId（若有）
                    ch_name = q2.get("chapter") or ""
                    if ch_name and ch_name in ch_name_to_id:
                        q2["chapterId"] = ch_name_to_id[ch_name]
                    resolved.append(q2)
                if missing_kp:
                    print(f"[warn] {missing_kp} 题的 kpNames 未能匹配到已建 KP（请先建章/KP）")
                st, j = api.req("POST", "/api/v1/question/import", body={"questions": resolved}, headers=H)
                if st == 200 and j.get("code") == 0:
                    n_q = j["data"].get("success") or 0
                    print(f"[init] 题目导入成功 {n_q}，失败 {j['data'].get('failed')}")
                else:
                    print(f"[warn] 题目导入失败: {j}")

    # 6) 可选：知识图谱边
    n_e = 0
    edges = (cfg.get("graph") or {}).get("edges") or []
    if edges:
        # 读取当前拓扑坐标，仅覆盖 edges
        st, j = api.req("GET", "/api/v1/teacher/graph/kp-topology", headers=H)
        if st != 200 or j.get("code") != 0:
            print(f"[warn] 读取图谱失败: {j}")
        else:
            topo = j["data"]
            nodes = [
                {"id": n["id"], "x": n["x"] if n.get("x") is not None else 120 + i * 70,
                 "y": n["y"] if n.get("y") is not None else 120 + (i // 6) * 80}
                for i, n in enumerate(topo.get("nodes") or [])
            ]
            payload_edges = []
            for e in edges:
                s = kp_name_to_id.get(e.get("source") or "")
                t = kp_name_to_id.get(e.get("target") or "")
                if not s or not t:
                    print(f"[warn] 图谱边 KP 未找到: {e}")
                    continue
                payload_edges.append({"source": s, "target": t, "relation": e.get("relation") or "pre"})
            st, j = api.req(
                "PUT",
                "/api/v1/teacher/graph/kp-topology",
                body={"nodes": nodes, "edges": payload_edges},
                headers=H,
            )
            if st == 200 and j.get("code") == 0:
                n_e = j["data"].get("savedEdges") or 0
                print(f"[init] 图谱边保存 {n_e}")
            else:
                print(f"[warn] 图谱保存失败: {j}")

    print()
    print("=" * 48)
    print("初始化完成")
    print(f"  courseId   : {api.course_id}")
    if invite:
        print(f"  inviteCode : {invite}  （发给学生 join）")
    print(f"  上传资源   : {n_up} 成功 / {n_fail} 失败")
    print(f"  题目       : {n_q}")
    print(f"  图谱边     : {n_e}")
    print("=" * 48)
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
