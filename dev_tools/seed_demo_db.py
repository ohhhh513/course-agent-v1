"""演示库的「账号 + 学情」生成器（独立脚本，不属于后端代码，不改任何后端逻辑）

分工（重要）
------------
**课程内容不用本脚本造**，交给项目自带的两个导入器（走 HTTP，等同教师在界面上操作）：

    1) 建课 / 章 / 知识点 / 上传资源
       python dev_tools/init_course.py --config dev_tools/demo_config.json \
              --teacher wangjg --password 123456
    2) 导入题库（按 KP 名称匹配）
       python dev_tools/import_questions.py --course <courseId> \
              --teacher wangjg --password 123456

本脚本只负责导入器**不覆盖**的两件事：

    init-db    建库（与当前模型同构）+ 写 1 管理员 / 1 教师 / 10 名学生 / 1 个班级
    activity   按人设生成 10 名学生的答题、练习会话、资源进度、打卡、消息、答疑，
               再由系统自身的 sync_user / detect_alerts 推导学习路径与预警
    accounts   只打印账号表（随时可查）

标准流程
--------
    # ① 建库 + 账号（离线）
    python dev_tools/seed_demo_db.py init-db

    # ② 起后端（指向上面的库；Windows PowerShell 示例）
    $env:DATABASE_URL="sqlite:///C:/workspace/course-agent-v1/backend/app/data/course_agent.db"
    cd backend; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

    # ③ 建课 + 章/KP + 上传资源（官方导入器）
    python dev_tools/init_course.py --config dev_tools/demo_config.json \
           --teacher wangjg --password 123456

    # ④ 导题库（官方导入器；记下 ③ 打印的 courseId）
    python dev_tools/import_questions.py --course <courseId> \
           --teacher wangjg --password 123456

    # ⑤ 停后端 → 生成学情（离线）
    python dev_tools/seed_demo_db.py activity --course <courseId>

    # ⑥ 重新起后端 → 用下面打印的账号登录演示

账号（演示口令，仅本地使用）
---------------------------
    管理员  admin  / admin
    教师    wangjg / 123456
    学生    stu01 … stu10 / 123456     （10 人画像见 PROFILES）
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")
DEFAULT_DB = os.path.join(BACKEND, "app", "data", "course_agent.db")

DEFAULT_PWD = "123456"

TEACHER = dict(user_id="T2026001", username="wangjg", name="王建国",
               title="副教授", dept="计算机科学与技术学院")
ADMIN = dict(user_id="ADMIN", username="admin", name="系统管理员")
CLASS = dict(class_id="CL2601", name="计算机 2601 班")

# ---------------------------------------------------------------------------
# 10 名学生的人设。字段含义：
#   ability   目标正确率基线（0~1）；coverage 覆盖知识点比例（按章顺序取前 N%）
#   vol       每个知识点作答题目数范围；res 资源学习比例；days 活跃天数
#   last_seen 最近一次学习距今天数；streak 最近连续天数
#   late_bias 越靠后的章节正确率偏移（负=越往后越差）
#   retry     做错后重做并答对的概率；seconds 每题作答秒数
# ---------------------------------------------------------------------------
PROFILES = [
    dict(no="2026010101", name="林书瑶", username="stu01", ability=0.94, coverage=1.00,
         vol=(4, 7), res=0.95, days=20, last_seen=0, streak=9, late_bias=0.02,
         retry=0.75, seconds=(35, 95),
         note="学霸：全章覆盖，正确率与资源完成度都高，连续学习 9 天"),
    dict(no="2026010102", name="陈嘉禾", username="stu02", ability=0.86, coverage=0.96,
         vol=(3, 6), res=0.88, days=17, last_seen=0, streak=5, late_bias=0.00,
         retry=0.65, seconds=(30, 90),
         note="优秀：稳定，个别难点失分"),
    dict(no="2026010103", name="吴思远", username="stu03", ability=0.78, coverage=0.88,
         vol=(3, 5), res=0.80, days=14, last_seen=0, streak=3, late_bias=-0.05,
         retry=0.55, seconds=(28, 80),
         note="良好：整体扎实，图论略弱"),
    dict(no="2026010104", name="周雨桐", username="stu04", ability=0.72, coverage=0.85,
         vol=(3, 5), res=0.90, days=15, last_seen=1, streak=2, late_bias=-0.18,
         retry=0.50, seconds=(30, 85),
         note="资源看得多、做题偏少；后半程章节明显下滑"),
    dict(no="2026010105", name="徐子墨", username="stu05", ability=0.66, coverage=0.80,
         vol=(3, 5), res=0.62, days=12, last_seen=0, streak=2, late_bias=-0.05,
         retry=0.45, seconds=(25, 75),
         note="中等：均衡但没有强项"),
    dict(no="2026010106", name="郑亦航", username="stu06", ability=0.55, coverage=0.78,
         vol=(3, 6), res=0.72, days=16, last_seen=0, streak=6, late_bias=-0.10,
         retry=0.40, seconds=(40, 110),
         note="很努力（学习天数多）但正确率不高，需要方法指导"),
    dict(no="2026010107", name="刘欣然", username="stu07", ability=0.48, coverage=0.70,
         vol=(3, 5), res=0.55, days=11, last_seen=1, streak=1, late_bias=-0.22,
         retry=0.35, seconds=(25, 80),
         note="中下：树、图两章明显薄弱"),
    dict(no="2026010108", name="王志豪", username="stu08", ability=0.38, coverage=0.55,
         vol=(2, 4), res=0.35, days=7, last_seen=3, streak=0, late_bias=-0.15,
         retry=0.25, seconds=(20, 60),
         note="较差：断断续续，多处红色预警"),
    dict(no="2026010109", name="孙梦琪", username="stu09", ability=0.30, coverage=0.42,
         vol=(2, 4), res=0.28, days=5, last_seen=2, streak=0, late_bias=-0.05,
         retry=0.20, seconds=(20, 55),
         note="差：只学到第 4 章左右，后半门课基本没碰"),
    dict(no="2026010110", name="何俊杰", username="stu10", ability=0.20, coverage=0.28,
         vol=(2, 3), res=0.12, days=3, last_seen=6, streak=0, late_bias=0.00,
         retry=0.15, seconds=(15, 50),
         note="最差：几乎不学，最近一次登录在 6 天前，预警最多"),
]


def log(msg=""):
    print(msg, flush=True)


def cn_to_utc_naive(dt_cn: datetime) -> datetime:
    """东八区 naive → UTC naive（库中统一存 UTC naive）。"""
    return dt_cn - timedelta(hours=8)


def parse_duration(text: str) -> int:
    if not text:
        return 0
    parts = [int(p) for p in str(text).split(":") if p.strip().isdigit()]
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def bind_env(db_path):
    """把后端模块指到目标库（必须在 import app.* 之前）。"""
    os.environ["DATABASE_URL"] = "sqlite:///" + db_path.replace("\\", "/")
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)


# ===========================================================================
# init-db：建库 + 管理员 / 教师 / 10 名学生 / 班级
# ===========================================================================
def cmd_config(args):
    """由 course_structure_ds.json 派生演示用配置（改课名/学期 + 把三类资源根指向仓库内素材）。"""
    src = os.path.join(REPO, "dev_tools", "course_structure_ds.json")
    with open(src, encoding="utf-8") as f:
        cfg = json.load(f)
    roots = os.path.join(REPO, "resources", "data-structures-1-9")
    cfg["baseUrl"] = args.base
    cfg.setdefault("course", {})
    cfg["course"]["name"] = args.name
    cfg["course"]["term"] = args.term
    cfg["course"]["useCourseId"] = None
    cfg["textbooksRoot"] = os.path.join(roots, "textbooks")
    cfg["videosRoot"] = os.path.join(roots, "videos")
    cfg["slidesRoot"] = os.path.join(roots, "slides")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    log(f"[config] 已生成 {args.out}")
    log(f"         课程名「{cfg['course']['name']}」 · 章 {len(cfg.get('chapters', []))} "
        f"· 资源 {len(cfg.get('resources', []))} 个")
    log(f"         资源根：{cfg['textbooksRoot']}\n"
        f"                  {cfg['videosRoot']}\n"
        f"                  {cfg['slidesRoot']}")


def cmd_init_db(args):
    if os.path.exists(args.db) and os.path.getsize(args.db) > 1024 and not args.force:
        raise SystemExit(f"目标库已存在且有内容：{args.db}\n确认覆盖请加 --force")
    if os.path.exists(args.db):
        os.remove(args.db)

    bind_env(args.db)
    from app.database import SessionLocal, engine, init_db
    from app.middleware.auth import hash_password
    from app.models.user import ClassInfo, TeacherClass, User

    init_db()
    engine.dispose()
    log(f"[init-db] 建表完成 → {args.db}")

    db = SessionLocal()
    pwd = hash_password(DEFAULT_PWD)
    db.add(User(user_id=ADMIN["user_id"], username=ADMIN["username"],
                password=hash_password("admin"), name=ADMIN["name"], role="admin",
                avatar_char="管", avatar_color="#64748b"))
    db.add(User(user_id=TEACHER["user_id"], username=TEACHER["username"], password=pwd,
                name=TEACHER["name"], role="teacher", title=TEACHER["title"],
                dept=TEACHER["dept"], avatar_char=TEACHER["name"][0],
                avatar_color="#2563eb"))
    db.add(ClassInfo(class_id=CLASS["class_id"], name=CLASS["name"],
                     student_count=len(PROFILES)))
    db.add(TeacherClass(teacher_user_id=TEACHER["user_id"], class_id=CLASS["class_id"],
                        class_name=CLASS["name"], student_count=len(PROFILES)))
    colors = ["#0ea5e9", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
              "#14b8a6", "#f97316", "#6366f1", "#ec4899", "#84cc16"]
    for i, s in enumerate(PROFILES):
        db.add(User(user_id=s["no"], username=s["username"], password=pwd, name=s["name"],
                    role="student", student_no=s["no"], class_name=CLASS["name"],
                    avatar_char=s["name"][0], avatar_color=colors[i % len(colors)]))
    db.commit()
    db.close()
    log(f"[init-db] 写入 1 管理员 + 1 教师 + {len(PROFILES)} 名学生 + 班级「{CLASS['name']}」")
    cmd_accounts(args)


# ===========================================================================
# activity：学情数据 + 学习路径 + 预警
# ===========================================================================
# ---- 知识图谱关系与「知识点介绍」：以【知识点名称】书写，脚本再解析成 id ----
# 前置链体现"这门课按什么顺序学"：绪论 → 线性表 → 链式结构 → 树/图 → 查找/排序
KP_PRE = {
    "算法与算法评价": ["数据结构概述"],
    "线性表": ["数据结构概述"],
    "顺序表": ["线性表"],
    "链表": ["线性表"],
    "栈": ["线性表"],
    "队列": ["线性表"],
    "栈与队列的应用": ["栈", "队列"],
    "串": ["线性表"],
    "串的模式匹配": ["串"],
    "多维数组与矩阵": ["线性表"],
    "广义表": ["多维数组与矩阵"],
    "树与二叉树": ["链表"],                    # 树/二叉树是链式结构的自然延伸
    "二叉树遍历": ["树与二叉树"],
    "树的应用": ["二叉树遍历"],
    "图的存储与遍历": ["树与二叉树"],
    "最短路径与生成树": ["图的存储与遍历"],
    "拓扑与关键路径": ["图的存储与遍历"],
    "查找": ["线性表", "顺序表"],                  # 顺序查找基于线性表，折半查找要求顺序存储
    "树形查找": ["树与二叉树", "查找"],
    "哈希表": ["查找"],
    "排序算法概述": ["算法与算法评价"],          # 排序比较以复杂度分析为基础
    "交换排序": ["排序算法概述"],
    "插入排序": ["排序算法概述"],
    "选择排序": ["排序算法概述"],
    "归并排序": ["排序算法概述"],
}

# 并列关系：同一层里"可以平行学、彼此没有先后依赖"的知识点
KP_PARALLEL = [
    ("顺序表", "链表"),
    ("栈", "队列"),
    ("最短路径与生成树", "拓扑与关键路径"),
    ("树形查找", "哈希表"),
    ("交换排序", "插入排序"),
    ("选择排序", "归并排序"),
]

# 知识点介绍（落 kp_details.summary；学生端与教师端的详情面板都会显示）
KP_SUMMARY = {
    "数据结构概述": "研究数据之间的逻辑关系、存储方式与基本运算的学科。本知识点讲清「逻辑结构」与「存储结构」的区别，以及抽象数据类型（ADT）的含义，是后面所有结构的总纲。",
    "算法与算法评价": "算法是求解问题的一系列有穷指令序列。这里聚焦评价方法：用大 O 记号描述时间/空间复杂度的渐进增长，区分最好、最坏与平均情况。",
    "线性表": "由 n 个同类型元素组成的有限序列，是最基础的线性结构。要掌握它的逻辑特性，以及顺序存储与链式存储两条实现路线各自的取舍。",
    "顺序表": "用一段连续内存依次存放元素，支持按下标随机访问。重点掌握插入/删除的平均移动次数、扩容代价，以及它与链表的选择依据。",
    "链表": "用「结点 + 指针」把元素串起来，已定位时插入删除只需改指针（O(1)），但不支持随机访问。需掌握单链表、双链表与循环链表的结构与常见操作。",
    "栈": "只允许在表尾插入和删除的「后进先出」结构。掌握顺序栈与链栈的实现，以及入栈、出栈、取栈顶时的边界判断。",
    "队列": "只允许一端进、另一端出的「先进先出」结构。重点掌握循环队列的判空与判满（少用一个存储单元，或增设标志位）。",
    "栈与队列的应用": "栈的典型用途：表达式求值、括号匹配、递归与函数调用栈；队列的典型用途：层次遍历、缓冲区与任务调度。",
    "串": "由零个或多个字符组成的有限序列，是内容受限的线性表。掌握串的基本操作（赋值、比较、连接、求子串）与存储方式。",
    "串的模式匹配": "在主串中定位子串出现的位置。重点是朴素 BF 算法与 KMP 算法的差异，以及 next 数组如何避免主串指针回退。",
    "多维数组与矩阵": "数组是下标的线性集合，多维数组可按行优先或列优先映射到一维内存。掌握对称矩阵、三角矩阵与稀疏矩阵的压缩存储思路。",
    "广义表": "表中元素既可以是单个元素、也可以是子表的推广线性表。掌握表头与表尾的概念，以及头尾链表存储表示。",
    "树与二叉树": "树描述层次结构，二叉树每个结点最多两棵子树。掌握二叉树的定义、主要性质（如第 i 层最多 2^(i-1) 个结点）与存储结构。",
    "二叉树遍历": "先序、中序、后序递归遍历与层次遍历，以及由两种遍历序列还原二叉树的方法。它是树形查找与图遍历的基础。",
    "树的应用": "树、森林与二叉树的相互转换；线索二叉树利用空指针域加速遍历；哈夫曼树以最短带权路径长度实现数据压缩编码。",
    "图的存储与遍历": "图由顶点和边组成，常用邻接矩阵与邻接表存储。深度优先（DFS）与广度优先（BFS）是图上的两种基本遍历策略。",
    "最短路径与生成树": "Prim 与 Kruskal 求最小生成树，Dijkstra 求单源最短路径，Floyd 求多源最短路径；注意各自适用的权值条件与复杂度。",
    "拓扑与关键路径": "有向无环图上的拓扑排序用于确定工序的先后次序；关键路径用于估算工程最短工期并找出瓶颈活动。",
    "查找": "在数据集合中定位目标记录。掌握顺序查找、折半查找与分块查找，并用平均查找长度（ASL）衡量它们的效率。",
    "树形查找": "二叉排序树（BST）、平衡二叉树（AVL）与 B 树/B+ 树。重点是插入删除后的结构调整，以及平衡性如何决定查找效率。",
    "哈希表": "用散列函数把关键字映射到存储位置，理想情况下查找可达 O(1)。掌握冲突处理（开放定址、链地址）与装填因子的影响。",
    "排序算法概述": "排序是按关键字重排记录。先建立整体框架：内部排序与外部排序、算法的稳定性，以及时间/空间代价的比较维度。",
    "交换排序": "冒泡排序与快速排序都属于交换排序。重点是快排的分区（partition）过程、枢轴选择，以及最坏情况退化到 O(n²) 的原因。",
    "插入排序": "直接插入排序在序列基本有序时效率很高；希尔排序按增量分组，让序列逐步趋于有序后再做插入排序。",
    "选择排序": "简单选择排序与堆排序。重点是建堆与筛选（调整）过程，以及堆排序为何能做到 O(n log n) 却不稳定。",
    "归并排序": "二路归并排序：先拆分到单元素，再两两合并有序表。它稳定、时间复杂度恒为 O(n log n)，代价是需要 O(n) 的辅助空间。",
}


def _http(base, method, path, token="", course="", body=None, timeout=60):
    """最小 HTTP 客户端（只用标准库，保持 dev_tools 既有风格）。"""
    import urllib.error
    import urllib.request
    url = base.rstrip("/") + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if course:
        req.add_header("X-Course-Id", course)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw[:300]}


def _kp_layout(ordered_ids, pre_edges):
    """按「最长前置链」分层排布坐标：x 随层级右移，同层按章序排列。"""
    parents = defaultdict(list)
    for s, t in pre_edges:
        parents[t].append(s)
    level = {}

    def lv(k, seen=()):
        if k in level:
            return level[k]
        ps = [p for p in parents.get(k, []) if p not in seen]
        level[k] = 0 if not ps else 1 + max(lv(p, seen + (k,)) for p in ps)
        return level[k]

    for k in ordered_ids:
        lv(k)
    buckets = defaultdict(list)
    for i, k in enumerate(ordered_ids):
        buckets[level[k]].append((i, k))
    nodes = []
    for lvl in sorted(buckets):
        for row, (_i, k) in enumerate(sorted(buckets[lvl])):
            nodes.append({"id": k, "x": 100 + lvl * 180, "y": 100 + row * 110})
    return nodes


def cmd_content(args):
    """把「前置/并列关系 + 知识点介绍」推到后端（全部走教师端官方接口，需服务在跑）。"""
    st, j = _http(args.base, "POST", "/api/v1/auth/login",
                  body={"username": args.teacher, "password": args.password,
                        "role": "teacher"})
    if st != 200 or j.get("code") != 0:
        raise SystemExit(f"教师登录失败：{j}")
    token = j["data"]["token"]
    log(f"[content] 教师登录成功: {args.teacher}")

    st, j = _http(args.base, "GET", "/api/v1/teacher/structure", token=token,
                  course=args.course)
    if st != 200 or j.get("code") != 0:
        raise SystemExit(f"读取课程结构失败：{j}")
    name2id, meta, ordered = {}, {}, []
    for g in j["data"]["chapters"]:
        for k in g.get("kps") or []:
            name2id[k["name"]] = k["id"]
            meta[k["id"]] = dict(name=k["name"], chapterId=g.get("id") or "",
                                 hours=k.get("hours") or 0, isKey=bool(k.get("isKey")))
            ordered.append(k["id"])
    log(f"[content] 课程 {args.course}：{len(ordered)} 个知识点")

    # 1) 坐标 + 并列关系。注意：拓扑接口是「覆盖式重写 pre/advance/parallel」，
    #    所以先写它，再用下面的 relations 接口补前置（那个接口只动 relation='pre'）。
    pre_pairs = [(name2id[a], name2id[b])
                 for b, pres in KP_PRE.items() if b in name2id
                 for a in pres if a in name2id]
    nodes = _kp_layout(ordered, pre_pairs)
    edges = [{"source": name2id[a], "target": name2id[b], "relation": "parallel"}
             for a, b in KP_PARALLEL if a in name2id and b in name2id]
    st, j = _http(args.base, "PUT", "/api/v1/teacher/graph/kp-topology", token=token,
                  course=args.course, body={"nodes": nodes, "edges": edges})
    if st != 200 or j.get("code") != 0:
        raise SystemExit(f"保存拓扑失败：{j}")
    log(f"[content] 坐标 {j['data']['savedNodes']} 个节点 / 并列关系 "
        f"{j['data']['savedEdges']} 条 / 未布点 {j['data']['pendingCount']}")

    # 2) 前置关系：官方接口含环检测，并双写 kp_details.pre_kp 与 post_kp
    n_pre = 0
    for kp_name, pres in KP_PRE.items():
        if kp_name not in name2id:
            continue
        pre_ids = [name2id[p] for p in pres if p in name2id]
        st, j = _http(args.base, "PUT",
                      f"/api/v1/teacher/structure/kps/{name2id[kp_name]}/relations",
                      token=token, course=args.course, body={"preKpIds": pre_ids})
        if st != 200 or j.get("code") != 0:
            raise SystemExit(f"保存前置失败（{kp_name}）：{j}")
        n_pre += len(pre_ids)
    log(f"[content] 前置关系 {n_pre} 条已保存（含环检测）")

    # 3) 知识点介绍
    n_sum = 0
    for kp_id in ordered:
        m = meta[kp_id]
        summary = KP_SUMMARY.get(m["name"])
        if not summary:
            continue
        st, j = _http(args.base, "PUT", f"/api/v1/teacher/structure/kps/{kp_id}",
                      token=token, course=args.course,
                      body={"name": m["name"], "chapterId": m["chapterId"],
                            "hours": m["hours"], "isKey": m["isKey"], "summary": summary})
        if st != 200 or j.get("code") != 0:
            raise SystemExit(f"保存介绍失败（{m['name']}）：{j}")
        n_sum += 1
    log(f"[content] 知识点介绍 {n_sum} 条已保存")

    st, j = _http(args.base, "GET", "/api/v1/teacher/graph/kp-topology", token=token,
                  course=args.course)
    rel = defaultdict(int)
    for e in j["data"]["edges"]:
        rel[e["relation"]] += 1
    log("[content] 复读校验：" + " / ".join(f"{k} {v} 条" for k, v in sorted(rel.items())))


def active_days_for(rng, profile, today, span):
    """活跃日期：先铺最近连续段（形成 streak），再在学期内随机补齐。"""
    days = set()
    start = today - timedelta(days=profile["last_seen"])
    for i in range(profile["streak"]):
        days.add(start - timedelta(days=i))
    rest = max(0, profile["days"] - len(days))
    pool = [today - timedelta(days=i) for i in range(span)]
    pool = [d for d in pool if d not in days and d <= start]
    if pool and rest:
        days |= set(rng.sample(pool, min(rest, len(pool))))
    return sorted(days)


def _wrong_key(q, rng):
    try:
        opts = json.loads(q.options or "[]")
        wrong = [o["key"] for o in opts if not o.get("right")]
        if wrong:
            return rng.choice(wrong)
    except Exception:
        pass
    for k in "ABCD":
        if k != q.answer:
            return k
    return "A"


def generate_activity(db, rng, profile, course_id, kps, pool_by_kp, days):
    """一名学生在一门课上的答题记录 + 练习会话。"""
    from app.models.practice import AnswerRecord, PracticeSession
    from app.models.question import Question

    if not kps or not days:
        return 0
    qmap = {q.q_id: q for q in db.query(Question).filter(
        Question.course_id == course_id, Question.status == "published").all()}
    cover_n = max(1, round(profile["coverage"] * len(kps)))
    covered = kps[:cover_n]

    planned = []
    for idx, kp in enumerate(covered):
        qs = [q for q in pool_by_kp.get(kp, []) if q.q_id in qmap]
        if not qs:
            continue
        ratio = idx / max(1, len(covered) - 1)
        base = clamp(profile["ability"] + profile["late_bias"] * ratio
                     + rng.gauss(0, 0.06), 0.02, 0.98)
        k = max(1, min(rng.randint(*profile["vol"]), len(qs)))
        for q in rng.sample(qs, k):
            day = rng.choice(days)
            pos = (day - days[0]).days / max(1, (days[-1] - days[0]).days)
            p = clamp(base - 0.16 * (1 - pos), 0.02, 0.98)   # 早期更差 → 成长轨迹有上升
            ok = rng.random() < p
            secs = rng.randint(*profile["seconds"])
            planned.append((day, kp, q, ok, secs))
            if not ok and rng.random() < profile["retry"]:
                later = [d for d in days if d > day]
                if later:      # 过几天重做并答对（错题本 + "越练越好"）
                    planned.append((rng.choice(later), kp, q, True,
                                    max(10, secs - rng.randint(0, 15))))
    if not planned:
        return 0
    planned.sort(key=lambda x: (x[0], x[2].q_id))

    by_day = defaultdict(list)
    for item in planned:
        by_day[item[0]].append(item)

    modes = ["order", "weak", "random", "order", "wrong", "random"]
    mode_i = n_ans = 0
    for day in sorted(by_day):
        items = by_day[day]
        rng.shuffle(items)
        cut = 0
        while cut < len(items):
            size = min(len(items) - cut, rng.randint(6, 10))
            chunk = items[cut:cut + size]
            cut += size
            sid = "PS" + "".join(rng.choice("0123456789abcdef") for _ in range(10))
            base_time = datetime.combine(day, time(19, 5)) + timedelta(
                minutes=rng.randint(0, 120))
            session = PracticeSession(
                session_id=sid, user_id=profile["no"], course_id=course_id,
                mode=modes[mode_i % len(modes)], total=len(chunk), status="finished",
                questions_snapshot=json.dumps(
                    [{"qId": q.q_id, "kpId": kp} for _, kp, q, _, _ in chunk],
                    ensure_ascii=False))
            # 必须先落会话行：answer_records.session_id 有外键，而两者没有 ORM 关系，
            # SQLAlchemy 不会自动按「先会话后答题」排序（否则 IntegrityError）。
            db.add(session)
            db.flush()
            mode_i += 1
            correct = dur = 0
            t = base_time
            for _, kp, q, ok, secs in chunk:
                t += timedelta(seconds=secs + rng.randint(5, 25))
                dur += secs
                correct += 1 if ok else 0
                db.add(AnswerRecord(
                    session_id=sid, user_id=profile["no"], course_id=course_id,
                    q_id=q.q_id, kp_id=kp,
                    my_answer=q.answer if ok else _wrong_key(q, rng),
                    correct_answer=q.answer, is_correct=1 if ok else 0, mastered=False,
                    duration_seconds=secs,
                    error_type="" if ok else (q.error_type or ""),
                    created_at=cn_to_utc_naive(t)))
                n_ans += 1
            session.correct = correct
            session.wrong = len(chunk) - correct
            session.accuracy = round(correct / len(chunk) * 100, 1)
            session.duration_seconds = dur
            session.created_at = cn_to_utc_naive(base_time)
            session.finished_at = cn_to_utc_naive(t)
    return n_ans


def generate_resource_progress(db, rng, profile, course_id, days):
    """资源学习进度 + 视频观看时长（打卡在 cmd_activity 里按人去重后统一写）。"""
    from app.models.course import Resource, ResourceProgress, ResourceStudyLog

    res = db.query(Resource).filter(Resource.course_id == course_id).all()
    if not res or not days:
        return 0
    rate0 = profile["res"]
    touched = rng.sample(res, int(round(len(res) * rate0))) if rate0 > 0 else []
    watch_by_day = {}          # 表上有 (user_id, day) 唯一约束 → 同一天只写一行
    for r in touched:
        rate = clamp(rate0 + rng.gauss(0, 0.1), 0.05, 1.0)
        day = rng.choice(days)
        when = cn_to_utc_naive(datetime.combine(day, time(20, 0))
                               + timedelta(minutes=rng.randint(0, 180)))
        if r.type == "video":
            total = parse_duration(r.duration) or 900
        else:
            total = (r.pages or 0) * 60 or 600
        db.add(ResourceProgress(user_id=profile["no"], res_id=r.res_id,
                                progress=int(round(rate * 100)), position=int(total * rate),
                                updated_at=when))
        if r.type == "video":
            for d in rng.sample(days, min(len(days), rng.randint(2, 5))):
                watch_by_day[d] = watch_by_day.get(d, 0) + rng.randint(420, 1500)
    for d, secs in watch_by_day.items():
        db.add(ResourceStudyLog(user_id=profile["no"], day=d.isoformat(),
                                watch_seconds=secs))
    return len(touched)


def generate_messages_and_chats(db, rng, profile, course_name, today, alerts_count):
    """站内消息 + 部分学生的 AI 答疑记录。"""
    from app.models.ai import ChatMessage, ChatSession
    from app.models.alert import Message

    def _mid():
        return "MSG" + "".join(rng.choice("0123456789abcdef") for _ in range(10))

    day = today - timedelta(days=rng.randint(0, 3))
    db.add(Message(msg_id=_mid(), user_id=profile["no"], from_user=TEACHER["user_id"],
                   from_name=TEACHER["name"], title="课程学习提醒",
                   content=f"「{course_name}」已进行到第 9 章，请按学习路径完成练习题。",
                   read=1 if profile["ability"] > 0.6 else 0,
                   created_at=cn_to_utc_naive(datetime.combine(day, time(9, 15)))))
    if alerts_count:
        db.add(Message(msg_id=_mid(), user_id=profile["no"], from_user="system",
                       from_name="系统", title=f"学习预警提醒（{alerts_count} 条）",
                       content=f"你在「{course_name}」中有 {alerts_count} 个知识点正确率偏低，"
                               f"建议尽快完成对应的靶向练习。",
                       read=0, created_at=cn_to_utc_naive(datetime.combine(day, time(9, 20)))))
    if profile["ability"] < 0.55:      # 学得吃力的学生才会去答疑
        kp = rng.choice(["树与二叉树", "图的存储与遍历", "排序算法概述"])
        sid = "CH" + "".join(rng.choice("0123456789abcdef") for _ in range(10))
        when = cn_to_utc_naive(datetime.combine(day, time(21, 5)))
        db.add(ChatSession(session_id=sid, user_id=profile["no"], course_id=COURSE_ID_HOLDER[0],
                           title=f"关于「{kp}」的疑问", kp_name=kp, flow_id="explain",
                           rounds=1, created_at=when, updated_at=when + timedelta(minutes=3)))
        db.flush()      # 先落会话行：chat_messages.session_id 有外键
        db.add(ChatMessage(session_id=sid, role="me", time_str="21:05", created_at=when,
                           content=f"「{kp}」这一块我不太理解，能帮我梳理一下重点吗？"))
        db.add(ChatMessage(session_id=sid, role="ai", method="guided", time_str="21:05",
                           citations="[]", tool_log="[]",
                           created_at=when + timedelta(seconds=40),
                           content=f"我们先从「{kp}」的定义入手：先确认它解决什么问题，再看典型"
                                   f"实现与复杂度，最后用一道小题检验。你觉得哪一步最容易出错？"))


COURSE_ID_HOLDER = [""]      # 供上面的消息/答疑函数取课程号（避免层层传参）


def cmd_activity(args):
    if not os.path.exists(args.db):
        raise SystemExit(f"数据库不存在：{args.db}（先跑 init-db）")
    bind_env(args.db)
    from sqlalchemy import func

    from app.database import SessionLocal
    from app.models.alert import Alert
    from app.models.checkin import StudyCheckin
    from app.models.course import Course, Resource
    from app.models.practice import AnswerRecord, PracticeSession
    from app.models.question import Question
    from app.models.user_course import UserCourse
    from app.routers.graph import (_mastery_for_user, _quiz_mastery_for_user,
                                   _status_from_quiz_mastery)
    from app.services.alert_detector import detect_alerts
    from app.services.learning_path import graph_nodes, sync_res_count, sync_user

    rng = random.Random(args.seed)
    today = date.today()
    COURSE_ID_HOLDER[0] = args.course
    db = SessionLocal()

    course = db.query(Course).filter(Course.course_id == args.course).first()
    if not course:
        raise SystemExit(f"课程不存在：{args.course}（先跑 init_course.py 建课）")

    # 可重复执行：先清掉这 10 名学生在**本课程**里上次生成的学情数据
    # （不动课程内容：章/KP/资源/题目，也不动其它课程的数据）
    from app.models.ai import ChatMessage, ChatSession
    from app.models.alert import Message
    from app.models.course import ResourceProgress, ResourceStudyLog
    uids = [s["no"] for s in PROFILES]
    old_chats = [r[0] for r in db.query(ChatSession.session_id).filter(
        ChatSession.user_id.in_(uids)).all()]
    n_clean = {}
    # 顺序要紧：答题先于会话（answer_records.session_id 有外键）
    n_clean["答题"] = db.query(AnswerRecord).filter(
        AnswerRecord.user_id.in_(uids)).delete(synchronize_session=False)
    n_clean["练习会话"] = db.query(PracticeSession).filter(
        PracticeSession.user_id.in_(uids)).delete(synchronize_session=False)
    n_clean["答疑"] = db.query(ChatMessage).filter(
        ChatMessage.session_id.in_(old_chats)).delete(synchronize_session=False) if old_chats else 0
    n_clean["答疑会话"] = db.query(ChatSession).filter(
        ChatSession.user_id.in_(uids)).delete(synchronize_session=False)
    n_clean["资源进度"] = db.query(ResourceProgress).filter(
        ResourceProgress.user_id.in_(uids)).delete(synchronize_session=False)
    n_clean["观看时长"] = db.query(ResourceStudyLog).filter(
        ResourceStudyLog.user_id.in_(uids)).delete(synchronize_session=False)
    n_clean["打卡"] = db.query(StudyCheckin).filter(
        StudyCheckin.user_id.in_(uids)).delete(synchronize_session=False)
    n_clean["预警"] = db.query(Alert).filter(
        Alert.user_id.in_(uids), Alert.course_id == args.course).delete(
            synchronize_session=False)
    n_clean["消息"] = db.query(Message).filter(
        Message.user_id.in_(uids)).delete(synchronize_session=False)
    db.commit()
    log("[activity] 清理上次生成的数据：" +
        " / ".join(f"{k} {v}" for k, v in n_clean.items()))

    # 1) 学生入课（教师已由建课接口写入成员表）
    joined = datetime.utcnow() - timedelta(days=args.days)
    have = {uc.user_id for uc in db.query(UserCourse).filter(
        UserCourse.course_id == args.course).all()}
    for s in PROFILES:
        if s["no"] not in have:
            db.add(UserCourse(user_id=s["no"], course_id=args.course,
                              role_in_course="student", joined_at=joined))
    db.commit()

    # 2) 知识点顺序（按章）+ 每题池
    ordered = [n.id for n in graph_nodes(db, args.course)]
    have_q = {r[0] for r in db.query(Question.kp_id).filter(
        Question.course_id == args.course,
        Question.status == "published").distinct().all()}
    kps = [k for k in ordered if k in have_q]
    pool_by_kp = defaultdict(list)
    for q in db.query(Question).filter(
            Question.course_id == args.course, Question.status == "published").all():
        pool_by_kp[q.kp_id].append(q)
    n_questions = db.query(func.count(Question.q_id)).filter(
        Question.course_id == args.course, Question.status == "published").scalar() or 0
    n_res = db.query(func.count(Resource.res_id)).filter(
        Resource.course_id == args.course).scalar() or 0
    log(f"[activity] 课程 {args.course}「{course.name}」："
        f"{len(ordered)} 个知识点 / {n_questions} 道题 / {n_res} 个资源")
    if not kps:
        raise SystemExit("该课程还没有已发布题目，先跑 import_questions.py")

    # 3) 逐人生成
    checkin_days = defaultdict(set)
    for s in PROFILES:
        days = active_days_for(rng, s, today, args.days)
        checkin_days[s["no"]] |= set(days)
        n = generate_activity(db, rng, s, args.course, kps, pool_by_kp, days)
        nr = generate_resource_progress(db, rng, s, args.course, days)
        log(f"    {s['name']}：答题 {n:>4} 条 · 资源 {nr:>2} 个 · 活跃 {len(days):>2} 天")
    db.commit()

    # 4) 打卡（登录即打卡；同一天只写一次）
    for uid, days in checkin_days.items():
        for d in sorted(days):
            db.add(StudyCheckin(user_id=uid, day=d, kind="study",
                                created_at=cn_to_utc_naive(datetime.combine(d, time(8, 30)))))
    db.commit()

    # 5) 学习路径：完全复用后端口径（掌握率 ∪ 资源完成率 → 状态）
    for s in PROFILES:
        uid = s["no"]
        mastery_map = _mastery_for_user(uid, db)
        quiz_map = _quiz_mastery_for_user(uid, db)
        has_quiz = set(quiz_map.keys())

        def state_of(kp_id, mm=mastery_map, qm=quiz_map, hq=has_quiz):
            return (mm.get(kp_id, 0),
                    _status_from_quiz_mastery(qm.get(kp_id, 0), mm.get(kp_id, 0),
                                              kp_id in hq))

        sync_user(db, uid, args.course, state_of)
    sync_res_count(db, args.course)
    db.commit()

    # 6) 预警：走系统自身的检测逻辑（阈值/等级/文案都由代码决定）
    log("[activity] 预警检测 → " + str(detect_alerts(db)))

    # 7) 消息 + 答疑（引用真实的预警条数）
    for s in PROFILES:
        n = db.query(Alert).filter(Alert.user_id == s["no"],
                                   Alert.status == "open").count()
        generate_messages_and_chats(db, rng, s, course.name, today, n)
    db.commit()

    # 8) 课程统计回填
    from app.models.graph import GraphNode
    course.chapters = db.query(func.count(GraphNode.id)).filter(
        GraphNode.course_id == args.course, GraphNode.graph_type == "chapter").scalar() or 0
    course.knowledge_points = db.query(func.count(GraphNode.id)).filter(
        GraphNode.course_id == args.course, GraphNode.graph_type == "knowledge").scalar() or 0
    course.resources = n_res
    course.questions = n_questions
    db.commit()

    summary(db, args.course)
    db.close()


# ===========================================================================
# accounts / summary
# ===========================================================================
def cmd_accounts(args):
    log("\n账号一览（演示口令）")
    log("-" * 96)
    log(f"{'角色':<6}{'姓名':<9}{'用户名':<10}{'密码':<10}{'用户ID/学号':<14}备注")
    log("-" * 96)
    log(f"{'管理员':<6}{ADMIN['name']:<9}{ADMIN['username']:<10}{'admin':<10}"
        f"{ADMIN['user_id']:<14}管理员后台 admin.html")
    log(f"{'教师':<6}{TEACHER['name']:<9}{TEACHER['username']:<10}{DEFAULT_PWD:<10}"
        f"{TEACHER['user_id']:<14}{TEACHER['title']} · {TEACHER['dept']}")
    for s in PROFILES:
        log(f"{'学生':<6}{s['name']:<9}{s['username']:<10}{DEFAULT_PWD:<10}"
            f"{s['no']:<14}{s['note']}")
    log("-" * 96)
    log(f"共 {len(PROFILES)} 名学生；学号前缀 20260101xx，用户名 stu01…stu10。")


def summary(db, course_id):
    from sqlalchemy import func

    from app.models.alert import Alert
    from app.models.practice import AnswerRecord, PracticeSession
    from app.services.scoring import quiz_accuracy_by_kp

    log("\n学情一览（由真实记录反算，和页面同口径）")
    log("-" * 108)
    log(f"{'姓名':<9}{'答题':>5}{'正确率':>8}{'覆盖知识点':>11}{'知识点平均正确率':>18}"
        f"{'练习次数':>9}{'预警':>6}  画像")
    log("-" * 108)
    for s in PROFILES:
        ar = db.query(func.count(AnswerRecord.id), func.sum(AnswerRecord.is_correct)).filter(
            AnswerRecord.user_id == s["no"], AnswerRecord.course_id == course_id).first()
        total_ans, correct = (ar[0] or 0), (ar[1] or 0)
        rate = round(correct / total_ans * 100, 1) if total_ans else 0.0
        acc = quiz_accuracy_by_kp(db, s["no"])
        acc = {k: v for k, v in acc.items()}          # 本课知识点
        avg = round(sum(v[0] for v in acc.values()) / len(acc), 1) if acc else 0.0
        sess = db.query(PracticeSession).filter(
            PracticeSession.user_id == s["no"],
            PracticeSession.course_id == course_id).count()
        alerts = db.query(Alert).filter(Alert.user_id == s["no"],
                                        Alert.course_id == course_id,
                                        Alert.status == "open").count()
        log(f"{s['name']:<9}{total_ans:>5}{rate:>7}%{len(acc):>11}{avg:>17}%"
            f"{sess:>9}{alerts:>6}  {s['note']}")
    log("-" * 108)
    cmd_accounts(argparse.Namespace(db=DEFAULT_DB))


# ===========================================================================
def parse_args():
    ap = argparse.ArgumentParser(description="演示库：账号 + 学情生成器")
    ap.add_argument("--db", default=DEFAULT_DB, help="目标数据库文件")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("init-db", help="建库 + 管理员/教师/10 学生/班级")
    p1.add_argument("--force", action="store_true", help="目标库有内容时也覆盖")

    p0 = sub.add_parser("config", help="生成演示用导入配置（给 init_course.py 用）")
    p0.add_argument("--out", default=os.path.join(REPO, "dev_tools", "demo_config.json"))
    p0.add_argument("--name", default="数据结构与算法", help="课程名")
    p0.add_argument("--term", default="2026-2027 学年 第一学期")
    p0.add_argument("--base", default="http://127.0.0.1:8000")

    p2 = sub.add_parser("activity", help="生成学情（需要课程内容已由导入器建好）")
    p2.add_argument("--course", required=True, help="课程 id（init_course.py 打印的 courseId）")
    p2.add_argument("--seed", type=int, default=20260924, help="随机种子")
    p2.add_argument("--days", type=int, default=30, help="学期回望天数")

    p3 = sub.add_parser("content", help="推送知识点关系与介绍（需服务在跑）")
    p3.add_argument("--course", required=True, help="课程 id")
    p3.add_argument("--base", default="http://127.0.0.1:8000", help="后端地址")
    p3.add_argument("--teacher", default=TEACHER["username"])
    p3.add_argument("--password", default=DEFAULT_PWD)

    sub.add_parser("accounts", help="只打印账号表")
    return ap.parse_args()


def main():
    args = parse_args()
    if args.cmd == "init-db":
        cmd_init_db(args)
    elif args.cmd == "config":
        cmd_config(args)
    elif args.cmd == "activity":
        cmd_activity(args)
    elif args.cmd == "content":
        cmd_content(args)
    else:
        cmd_accounts(args)


if __name__ == "__main__":
    main()
