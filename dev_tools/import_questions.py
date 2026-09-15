"""
开发用：通过 HTTP API 批量导入已转换题库（questions_after_class_import.json）。

隔离：仅 dev_tools；不随服务启动；只打已运行后端。

用法（项目根，先启动后端）:
  python dev_tools/import_questions.py
  python dev_tools/import_questions.py --course CXXXXXXX
  python dev_tools/import_questions.py --file dev_tools/questions_after_class_import.json --teacher dev_teacher --password 123456
  python dev_tools/import_questions.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
DEFAULT_FILE = HERE / "questions_after_class_import.json"
BATCH = 50


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api_req(base, method, path, token="", course_id="", body=None, timeout=180):
    url = base.rstrip("/") + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if course_id:
        r.add_header("X-Course-Id", course_id)
    op = opener()
    try:
        with op.open(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"code": e.code, "message": raw[:300]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="导入转换后的题库（HTTP API）")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--teacher", default="dev_teacher")
    ap.add_argument("--password", default="123456")
    ap.add_argument("--course", default="", dest="course_id", help="目标课程 ID（必填，除非 --list-only）")
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--dry-run", action="store_true", help="只校验文件与 KP 匹配，不调用导入")
    args = ap.parse_args(argv)

    qpath = Path(args.file)
    if not qpath.is_absolute():
        qpath = ROOT / qpath
    if not qpath.is_file():
        print(f"[error] 题库文件不存在: {qpath}")
        return 1

    if not args.course_id:
        print("[error] 请指定 --course <courseId>（题库将写入该课）")
        print("        课号可从教师端顶栏课程下拉，或 init_course 输出的 courseId 获取")
        return 1

    qlist = json.loads(qpath.read_text(encoding="utf-8"))
    if not isinstance(qlist, list) or not qlist:
        print("[error] 题库必须是非空 JSON 数组")
        return 1
    print(f"[load] {qpath.name}: {len(qlist)} 题")

    base = args.base.rstrip("/")
    st, j = api_req(base, "POST", "/api/v1/auth/login", body={
        "username": args.teacher,
        "password": args.password,
    })
    if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
        print(f"[error] 教师登录失败: {j}")
        return 1
    token = j["data"]["token"]
    cid = args.course_id
    print(f"[auth] teacher={args.teacher} course={cid}")

    # 结构：解析 kpNames → kp_id，并校验教师可访问该课
    st, j = api_req(base, "GET", "/api/v1/teacher/structure", token=token, course_id=cid)
    if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
        print(f"[error] 无法读取课程结构（未加入该课或课号错误）: {j.get('message') or j.get('detail') if isinstance(j, dict) else j}")
        return 1
    topo = j["data"]
    kp_name_to_id = {}
    for k in topo.get("kpOptions") or []:
        kp_name_to_id[k["name"]] = k["id"]
    ch_name_to_id = {c["name"]: c["id"] for c in (topo.get("chapterOptions") or [])}
    print(f"[struct] KP {len(kp_name_to_id)} · 章 {len(ch_name_to_id)}")

    resolved = []
    miss_kp = 0
    miss_samples = []
    for q in qlist:
        q2 = dict(q)
        names = q2.pop("kpNames", None) or q2.pop("kp_names", None) or []
        ids = [kp_name_to_id[n] for n in names if n in kp_name_to_id]
        if names and not ids:
            miss_kp += 1
            if len(miss_samples) < 5:
                miss_samples.append((q2.get("stem", "")[:24], names))
        if ids:
            q2["kp_ids"] = ids
            q2["kp_id"] = ids[0]
        ch = q2.get("chapter") or ""
        if ch and ch in ch_name_to_id:
            q2["chapterId"] = ch_name_to_id[ch]
        # 去掉仅用于中间态的 sourceId（可选保留不影响）
        resolved.append(q2)

    if miss_kp:
        print(f"[warn] {miss_kp} 题 kpNames 未匹配到结构中 KP，示例: {miss_samples}")
    if args.dry_run:
        sample = resolved[0] if resolved else {}
        print("[dry-run] 第一题字段:", sorted(sample.keys()))
        print("[dry-run] 已 KP:", sum(1 for x in resolved if x.get("kp_ids")))
        print("[dry-run] 未调用 POST /question/import")
        return 0

    # 分批导入
    total_ok = total_fail = 0
    all_errors = []
    for i in range(0, len(resolved), max(1, args.batch)):
        chunk = resolved[i : i + args.batch]
        st, j = api_req(
            base,
            "POST",
            "/api/v1/question/import",
            token=token,
            course_id=cid,
            body={"questions": chunk},
            timeout=300,
        )
        if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
            print(f"[error] batch {i // args.batch + 1} 失败: {j}")
            total_fail += len(chunk)
            if isinstance(j, dict) and j.get("message"):
                all_errors.append(str(j["message"]))
            continue
        d = j.get("data") or {}
        ok_n = int(d.get("success") or 0)
        fail_n = int(d.get("failed") or 0)
        total_ok += ok_n
        total_fail += fail_n
        print(f"  batch {i // args.batch + 1}: +{ok_n} ok / {fail_n} fail  (累计 {total_ok})")
        for e in (d.get("errors") or [])[:5]:
            all_errors.append(str(e))

    print()
    print("=" * 48)
    print("题库导入完成")
    print(f"  courseId : {cid}")
    print(f"  成功     : {total_ok}")
    print(f"  失败     : {total_fail}")
    if all_errors:
        print("  错误样例:")
        for e in all_errors[:8]:
            print("   -", e)
    print("=" * 48)
    return 0 if total_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
