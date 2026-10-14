"""dev_tools 交互工具：终端问答、列课、路径根替换（不进入业务启动链）。"""
from __future__ import annotations

import getpass
import json
import urllib.error
import urllib.request
from pathlib import Path


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(base: str, method: str, path: str, token="", course_id="", body=None, timeout=120):
    url = base.rstrip("/") + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if course_id:
        r.add_header("X-Course-Id", course_id)
    try:
        with opener().open(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"code": e.code, "message": raw[:300]}


def ask(prompt: str, default: str = "", allow_empty: bool = False) -> str:
    if allow_empty:
        s = input(f"{prompt}: ").strip()
        return s
    if default:
        s = input(f"{prompt} [{default}]: ").strip()
        return s or default
    while True:
        s = input(f"{prompt}: ").strip()
        if s:
            return s
        print("  （不能为空）")


def ask_password(prompt: str = "密码", default: str = "") -> str:
    if default:
        # 非交互环境可回退
        try:
            s = getpass.getpass(f"{prompt} [{default}]: ").strip()
        except Exception:
            s = input(f"{prompt} [{default}]: ").strip()
        return s or default
    try:
        return getpass.getpass(f"{prompt}: ").strip()
    except Exception:
        return input(f"{prompt}: ").strip()


def ask_choice(prompt: str, options: list[str], default_idx: int = 0) -> int:
    print(prompt)
    if not options:
        raise ValueError("无选项")
    for i, opt in enumerate(options, 1):
        mark = " *" if i - 1 == default_idx else ""
        print(f"  {i}. {opt}{mark}")
    raw = input(f"输入序号（回车={default_idx + 1}）: ").strip()
    if not raw:
        return default_idx
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return idx
    except ValueError:
        pass
    print("无效，使用默认")
    return default_idx


def _norm_root(root: str) -> str:
    """规范化根目录：去引号、统一斜杠、去尾部分隔符。"""
    s = (root or "").strip().strip('"').strip("'").strip()
    s = s.replace("\\", "/")
    while s.endswith("/"):
        s = s[:-1]
    return s


def _clean_file_path(path: str) -> str:
    """规范化资源文件绝对/相对路径：去引号、斜杠、消除 root/root 重复段。"""
    s = (path or "").strip().strip('"').strip("'").strip().replace("\\", "/")
    # 去掉连续重复的 textbooks|videos|slides 目录段（如 .../textbooks/textbooks/x.pdf）
    for seg in ("textbooks", "videos", "slides"):
        dup = f"/{seg}/{seg}/"
        while dup in f"/{s}/":
            s = s.replace(dup, f"/{seg}/")
    return s


def _kind_from_path(path: str) -> str:
    """按扩展名/路径片段归类: textbooks | videos | slides"""
    p = path.replace("\\", "/").lower()
    if p.endswith((".mp4", ".avi", ".mov", ".mkv")) or "/video" in p or p.endswith(".webm"):
        return "videos"
    if p.endswith((".ppt", ".pptx")) or "/slide" in p or "/ppt" in p:
        return "slides"
    if p.endswith((".pdf", ".doc", ".docx")) or "/textbook" in p or "/doc" in p:
        return "textbooks"
    return "other"


def apply_path_roots(cfg: dict, roots: dict | None, single_root: str = "") -> dict:
    """按类型根目录 / 单根 / 占位符 重写 resources[].file。

    roots 支持: {textbooks, videos, slides}；缺省可回落 single_root。
    占位符: {textbooksRoot} {videosRoot} {slidesRoot} {resourcesRoot}
    """
    roots = roots or {}
    tb = _norm_root(roots.get("textbooks") or "")
    vd = _norm_root(roots.get("videos") or "")
    sl = _norm_root(roots.get("slides") or "")
    all_root = _norm_root(single_root or roots.get("resourcesRoot") or "")

    # 若只填了统一 root，且路径名以 textbooks/videos/slides 结尾 → 视为对应类型根
    if all_root:
        leaf = all_root.split("/")[-1].lower()
        if leaf == "textbooks" and not tb:
            tb = all_root
        elif leaf == "videos" and not vd:
            vd = all_root
        elif leaf == "slides" and not sl:
            sl = all_root
        else:
            tb = tb or all_root
            vd = vd or all_root
            sl = sl or all_root
    if not any((tb, vd, sl, all_root)):
        return cfg

    out = dict(cfg)
    res = []
    for item in out.get("resources") or []:
        item = dict(item)
        f = item.get("file") or ""
        path = f.replace("\\", "/")
        name = Path(path).name
        kind = _kind_from_path(path)

        # 1) 显式占位符
        if "{textbooksRoot}" in path and tb:
            path = path.replace("{textbooksRoot}", tb)
        if "{videosRoot}" in path and vd:
            path = path.replace("{videosRoot}", vd)
        if "{slidesRoot}" in path and sl:
            path = path.replace("{slidesRoot}", sl)
        if "{resourcesRoot}" in path and all_root:
            path = path.replace("{resourcesRoot}", all_root)

        # 2) 仍含未解析占位 → 按类型根 + 文件名
        if "{textbooksRoot}" in path and tb:
            path = f"{tb}/{name}"
        elif "{videosRoot}" in path and vd:
            path = f"{vd}/{name}"
        elif "{slidesRoot}" in path and sl:
            path = f"{sl}/{name}"
        elif "{resourcesRoot}" in path and all_root:
            path = f"{all_root}/{name}"

        # 3) 原绝对路径：保留「data-structures-1-9/」之后的相对段，替换对应类型根
        marker = "data-structures-1-9/"
        if marker in path:
            rel = path.split(marker, 1)[1]
            kind = _kind_from_path(rel) if kind == "other" else kind
            base = tb if kind == "textbooks" else vd if kind == "videos" else sl if kind == "slides" else all_root
            if base:
                # 类型根若直接指向 textbooks/videos/slides 文件夹，则去掉前缀子目录
                for prefix in ("textbooks/", "videos/", "slides/"):
                    if rel.startswith(prefix):
                        rel = rel[len(prefix):]
                        break
                path = f"{base}/{rel}"

        item["file"] = _clean_file_path(path)
        res.append(item)
    out["resources"] = res
    if tb:
        out["textbooksRoot"] = tb
    if vd:
        out["videosRoot"] = vd
    if sl:
        out["slidesRoot"] = sl
    if all_root:
        out["resourcesRoot"] = all_root
    return out


# 兼容旧调用
def apply_resources_root(cfg: dict, root: str) -> dict:
    return apply_path_roots(cfg, {}, single_root=root)


def print_chapters(chapters: list) -> None:
    print("\n当前章节 / 知识点：")
    if not chapters:
        print("  （空）")
        return
    for i, ch in enumerate(chapters, 1):
        kps = ch.get("kps") or []
        print(f"  {i}. {ch.get('name')}")
        print(f"     KP: {', '.join(kps) if kps else '（无）'}")


def prompt_edit_chapters(chapters: list) -> list:
    """交互编辑章/KP 列表；返回新列表。按 n 直接使用当前结构。"""
    chapters = [dict(c) for c in (chapters or [])]
    for ch in chapters:
        ch["kps"] = list(ch.get("kps") or [])
    print("\n—— 章节与知识点（可选编辑）——")
    print_chapters(chapters)
    raw = ask("是否编辑章/KP？(n=直接使用 / e=编辑)", "n").lower()
    if raw not in ("e", "y", "yes", "edit"):
        return chapters

    while True:
        print_chapters(chapters)
        print("\n操作:")
        print("  1 修改某章名称")
        print("  2 修改某章知识点（逗号分隔）")
        print("  3 新增章节（含 KP）")
        print("  4 删除某章")
        print("  5 完成，按当前结构继续")
        op = ask("选择操作", "5")
        if op == "5":
            break
        if op == "1" and chapters:
            i = ask_choice("选择章节", [c.get("name") or ""], 0)
            name = ask("新章名", chapters[i].get("name") or "")
            if name:
                chapters[i]["name"] = name
        elif op == "2" and chapters:
            i = ask_choice("选择章节", [c.get("name") or ""], 0)
            old = ", ".join(chapters[i].get("kps") or [])
            s = ask("知识点（逗号分隔）", old)
            chapters[i]["kps"] = [x.strip() for x in s.split(",") if x.strip()]
        elif op == "3":
            name = ask("新章节名称（如：第10章 图论进阶）")
            if not name:
                continue
            s = ask("该章知识点（逗号分隔）", "")
            chapters.append({
                "name": name,
                "kps": [x.strip() for x in s.split(",") if x.strip()],
            })
        elif op == "4" and chapters:
            i = ask_choice("删除哪一章？", [c.get("name") or ""], 0)
            confirm = ask(f"确认删除「{chapters[i].get('name')}」？(y/n)", "n")
            if confirm.lower() in ("y", "yes"):
                del chapters[i]
        else:
            print("无效操作")
    print_chapters(chapters)
    save = ask("是否写回配置文件？(y/n)", "n")
    if save.lower() in ("y", "yes"):
        return chapters  # 由调用方负责写回
    return chapters


def list_teachers(base: str, admin_user: str = "admin", admin_pass: str = "admin") -> list[dict]:
    """尝试用管理员列出教师账号；失败返回 []。"""
    try:
        st, j = http_json(base, "POST", "/api/v1/auth/login", body={
            "username": admin_user, "password": admin_pass, "role": "admin",
        })
        if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
            return []
        token = j["data"]["token"]
        st, j = http_json(base, "GET", "/api/v1/admin/users", token=token, body=None)
        if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
            return []
        return [u for u in (j.get("data") or {}).get("list") or [] if u.get("role") == "teacher"]
    except Exception:
        return []


def pick_teacher(base: str, default_user: str = "") -> str:
    """交互：从管理员列表选教师，或手输用户名。返回用户名。"""
    teachers = list_teachers(base)
    if teachers:
        options = [f"{t.get('username')}  {t.get('name') or ''}".strip() for t in teachers]
        options.append("手动输入用户名")
        print("\n请选择教师账号（需已用管理员创建）：")
        idx = ask_choice("教师列表", options, default_idx=0)
        if idx < len(teachers):
            return teachers[idx]["username"]
        return ask("教师用户名")
    print("\n（未能读取教师列表；管理员需已登录态或 admin/admin 可用）")
    return ask("教师用户名", default_user or "")


def list_teacher_courses(base: str, token: str) -> list[dict]:
    st, j = http_json(base, "GET", "/api/v1/course/my", token=token)
    if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
        return []
    data = j.get("data") or []
    return [c for c in data if (c.get("role") or "") == "teacher"]


def login_teacher(base: str, username: str, password: str) -> str:
    st, j = http_json(base, "POST", "/api/v1/auth/login", body={
        "username": username, "password": password, "role": "teacher",
    })
    if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
        msg = j.get("message") or j.get("detail") if isinstance(j, dict) else j
        raise RuntimeError(f"教师登录失败: {msg}")
    return j["data"]["token"]


def prompt_teacher(base: str, default_user: str = "", default_pass: str = "") -> tuple[str, str, str]:
    """交互输入教师并登录，返回 (username, password, token)"""
    username = ask("教师用户名", default_user)
    password = ask_password("教师密码", default_pass)
    token = login_teacher(base, username, password)
    print(f"[ok] 教师登录成功: {username}")
    return username, password, token


def prompt_course(token: str, base: str, create_name: str = "数据结构与算法") -> tuple[str, str]:
    """列出教师已有课程供选择；也可新建。返回 (courseId, inviteCode)"""
    courses = list_teacher_courses(base, token)
    print("\n—— 选择课程 ——")
    if courses:
        print(f"当前教师已有 {len(courses)} 门课：")
        for i, c in enumerate(courses, 1):
            print(f"  {i}. {c.get('courseId')}  {c.get('name')}")
        options = [f"{c.get('courseId')}  {c.get('name')}" for c in courses]
        options.append("新建课程（输入名称）")
        idx = ask_choice("请选择：使用已有课 / 新建", options, default_idx=0)
        if idx < len(courses):
            cid = courses[idx]["courseId"]
            invite = courses[idx].get("inviteCode") or ""
            print(f"[ok] 使用已有课程 {cid} · {courses[idx].get('name')}")
            return cid, invite
    else:
        print("（该教师暂无课程，将新建）")

    print("\n—— 新建课程 ——")
    print(f"直接回车使用默认名称；也可输入自定义名称。")
    name = ask(f"课程名称", create_name) or create_name
    print(f"[info] 将创建课程：{name}")
    st, j = http_json(base, "POST", "/api/v1/teacher/courses", token=token, body={
        "name": name, "term": "",
    })
    if st != 200 or not isinstance(j, dict) or j.get("code") != 0:
        raise RuntimeError(f"建课失败: {j.get('message') if isinstance(j, dict) else j}")
    cid = j["data"]["courseId"]
    invite = j["data"].get("inviteCode") or ""
    print(f"[ok] 已新建课程 {cid}  邀请码={invite}")
    return cid, invite
