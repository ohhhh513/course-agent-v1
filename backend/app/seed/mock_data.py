"""
Mock 数据 —— 真实可溯源的 transaction 种子数据生成
所有 transaction 记录均归属到具体 user_id，不再有跨用户共享的预置快照。
"""
import json
import random
from datetime import datetime, timedelta

# 固定种子，保证每次运行生成完全相同的数据
random.seed(42)

# ============ 时间基准 ============
BASE = datetime(2026, 9, 2, 17, 0, 0)   # "今天" 17:00


def days_ago(n, hour_jitter=6):
    """返回 BASE - n 天 ± 若干小时的随机 datetime（永远是过去时间）"""
    # hour_jitter 只用负值或 0，保证结果 <= BASE
    return BASE - timedelta(
        days=n,
        hours=abs(random.randint(-hour_jitter, 0)),
        minutes=random.randint(0, 59),
    )


# ============ 学生账号（12 人） ============
STUDENT_ACCOUNTS = [
    {"username": "student", "password": "123456", "role": "student", "name": "陈思远",
     "user_id": "S20260317", "student_no": "2023110317", "class_name": "计算机 2301 班"},
    {"username": "s_zzh", "password": "123456", "role": "student", "name": "赵梓涵",
     "user_id": "S20260322", "student_no": "2023110322", "class_name": "计算机 2301 班"},
    {"username": "s_wjh", "password": "123456", "role": "student", "name": "吴嘉豪",
     "user_id": "S20260333", "student_no": "2023110333", "class_name": "计算机 2301 班"},
    {"username": "s_xzm", "password": "123456", "role": "student", "name": "徐子墨",
     "user_id": "S20260337", "student_no": "2023110337", "class_name": "计算机 2301 班"},
    {"username": "s_lhr", "password": "123456", "role": "student", "name": "林浩然",
     "user_id": "S20260341", "student_no": "2023110341", "class_name": "计算机 2301 班"},
    {"username": "s_ytl", "password": "123456", "role": "student", "name": "周雨桐",
     "user_id": "S20260329", "student_no": "2023110329", "class_name": "计算机 2301 班"},
    {"username": "s_wzh", "password": "123456", "role": "student", "name": "王志豪",
     "user_id": "S20260319", "student_no": "2023110319", "class_name": "计算机 2301 班"},
    {"username": "s_lxr", "password": "123456", "role": "student", "name": "刘欣然",
     "user_id": "S20260325", "student_no": "2023110325", "class_name": "计算机 2301 班"},
    {"username": "s_sbw", "password": "123456", "role": "student", "name": "孙博文",
     "user_id": "S20260330", "student_no": "2023110330", "class_name": "计算机 2301 班"},
    {"username": "s_cxl", "password": "123456", "role": "student", "name": "陈欣怡",
     "user_id": "S20260318", "student_no": "2023110318", "class_name": "计算机 2301 班"},
    {"username": "s_lyx", "password": "123456", "role": "student", "name": "李雅琪",
     "user_id": "S20260321", "student_no": "2023110321", "class_name": "计算机 2301 班"},
    {"username": "s_hzx", "password": "123456", "role": "student", "name": "何子轩",
     "user_id": "S20260328", "student_no": "2023110328", "class_name": "计算机 2301 班"},
]

DEFAULT_ACCOUNTS = STUDENT_ACCOUNTS + [
    {"username": "teacher", "password": "123456", "role": "teacher", "name": "李文博",
     "user_id": "T100286", "title": "副教授", "dept": "计算机科学与技术学院"},
]

# ============ 知识图谱节点（公共数据，全部保留） ============
MOCK_GRAPH_NODES = [
    {"id": "KP01", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "算法与复杂度", "category": 0, "chapter": "第1章", "mastery": 92, "difficulty": 2, "is_key": True, "hours": 4},
    {"id": "KP02", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "时间复杂度分析", "category": 0, "chapter": "第1章", "mastery": 88, "difficulty": 3, "is_key": True, "hours": 4},
    {"id": "KP11", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "线性表定义", "category": 0, "chapter": "第2章", "mastery": 95, "difficulty": 1, "is_key": False, "hours": 2},
    {"id": "KP12", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "顺序表", "category": 0, "chapter": "第2章", "mastery": 90, "difficulty": 2, "is_key": True, "hours": 4},
    {"id": "KP13", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "单链表", "category": 0, "chapter": "第2章", "mastery": 85, "difficulty": 3, "is_key": True, "hours": 6},
    {"id": "KP14", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "双向 / 循环链表", "category": 2, "chapter": "第2章", "mastery": 68, "difficulty": 3, "is_key": False, "hours": 4},
    {"id": "KP21", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "栈的定义与实现", "category": 0, "chapter": "第3章", "mastery": 87, "difficulty": 2, "is_key": True, "hours": 4},
    {"id": "KP22", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "队列的定义与实现", "category": 0, "chapter": "第3章", "mastery": 82, "difficulty": 2, "is_key": True, "hours": 4},
    {"id": "KP23", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "循环队列判空判满", "category": 2, "chapter": "第3章", "mastery": 61, "difficulty": 4, "is_key": True, "hours": 2},
    {"id": "KP24", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "栈的典型应用", "category": 0, "chapter": "第3章", "mastery": 79, "difficulty": 3, "is_key": False, "hours": 4},
    {"id": "KP31", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "二叉树基本概念", "category": 1, "chapter": "第4章", "mastery": 72, "difficulty": 3, "is_key": True, "hours": 4},
    {"id": "KP32", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "二叉树的遍历", "category": 1, "chapter": "第4章", "mastery": 66, "difficulty": 4, "is_key": True, "hours": 6},
    {"id": "KP33", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "线索二叉树", "category": 3, "chapter": "第4章", "mastery": 0, "difficulty": 4, "is_key": False, "hours": 4},
    {"id": "KP34", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "树与森林的转换", "category": 3, "chapter": "第4章", "mastery": 0, "difficulty": 3, "is_key": False, "hours": 4},
    {"id": "KP44", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "哈夫曼树与编码", "category": 2, "chapter": "第4章", "mastery": 55, "difficulty": 4, "is_key": True, "hours": 4},
    {"id": "KP41", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "图的定义与术语", "category": 0, "chapter": "第5章", "mastery": 80, "difficulty": 2, "is_key": False, "hours": 2},
    {"id": "KP42", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "图的存储结构", "category": 2, "chapter": "第5章", "mastery": 63, "difficulty": 3, "is_key": True, "hours": 4},
    {"id": "KP43", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "图的遍历 DFS/BFS", "category": 1, "chapter": "第5章", "mastery": 70, "difficulty": 4, "is_key": True, "hours": 6},
    {"id": "KP51", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "最小生成树", "category": 2, "chapter": "第5章", "mastery": 58, "difficulty": 4, "is_key": True, "hours": 4},
    {"id": "KP52", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "最短路径 Dijkstra", "category": 4, "chapter": "第5章", "mastery": 41, "difficulty": 5, "is_key": True, "hours": 6},
    {"id": "KP53", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "拓扑排序", "category": 3, "chapter": "第5章", "mastery": 0, "difficulty": 4, "is_key": False, "hours": 4},
    {"id": "KP61", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "查找的基本概念", "category": 3, "chapter": "第6章", "mastery": 0, "difficulty": 1, "is_key": False, "hours": 2},
    {"id": "KP62", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "二分查找", "category": 3, "chapter": "第6章", "mastery": 0, "difficulty": 3, "is_key": True, "hours": 4},
    {"id": "KP63", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "二叉排序树", "category": 3, "chapter": "第6章", "mastery": 0, "difficulty": 4, "is_key": True, "hours": 6},
    {"id": "KP64", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "哈希表", "category": 3, "chapter": "第6章", "mastery": 0, "difficulty": 4, "is_key": True, "hours": 4},
    {"id": "KP71", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "插入 / 冒泡排序", "category": 3, "chapter": "第7章", "mastery": 0, "difficulty": 2, "is_key": False, "hours": 4},
    {"id": "KP72", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "快速排序", "category": 3, "chapter": "第7章", "mastery": 0, "difficulty": 4, "is_key": True, "hours": 4},
    {"id": "KP73", "graph_type": "knowledge", "course_id": "C2026DS001", "name": "堆排序", "category": 3, "chapter": "第7章", "mastery": 0, "difficulty": 5, "is_key": True, "hours": 4},
    {"id": "PB1", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何为地图导航设计最优路线？", "category": 0, "level": 1, "related_kp": 6, "error_rate": 38, "count": 0},
    {"id": "PB1-1", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何抽象城市路网？", "category": 1, "level": 2, "related_kp": 2, "error_rate": 21, "count": 0},
    {"id": "PB1-2", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何存储带权图？", "category": 1, "level": 2, "related_kp": 2, "error_rate": 33, "count": 0},
    {"id": "PB1-3", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何求单源最短路径？", "category": 1, "level": 2, "related_kp": 3, "error_rate": 52, "count": 0},
    {"id": "KP41", "graph_type": "problem", "course_id": "C2026DS001", "name": "图的定义与术语", "category": 2, "level": 3, "related_kp": 0, "error_rate": 0, "count": 0},
    {"id": "KP42", "graph_type": "problem", "course_id": "C2026DS001", "name": "图的存储结构", "category": 2, "level": 3, "related_kp": 0, "error_rate": 0, "count": 0},
    {"id": "KP52", "graph_type": "problem", "course_id": "C2026DS001", "name": "最短路径 Dijkstra", "category": 2, "level": 3, "related_kp": 0, "error_rate": 0, "count": 0},
    {"id": "EC1", "graph_type": "problem", "course_id": "C2026DS001", "name": "错题簇：贪心松弛顺序混乱", "category": 3, "level": 4, "related_kp": 0, "error_rate": 0, "count": 26},
    {"id": "EC2", "graph_type": "problem", "course_id": "C2026DS001", "name": "错题簇：邻接矩阵/表选择错误", "category": 3, "level": 4, "related_kp": 0, "error_rate": 0, "count": 18},
    {"id": "PB2", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何实现表达式求值器？", "category": 0, "level": 1, "related_kp": 4, "error_rate": 24, "count": 0},
    {"id": "PB2-1", "graph_type": "problem", "course_id": "C2026DS001", "name": "中缀如何转后缀？", "category": 1, "level": 2, "related_kp": 2, "error_rate": 29, "count": 0},
    {"id": "PB2-2", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何用栈完成求值？", "category": 1, "level": 2, "related_kp": 2, "error_rate": 18, "count": 0},
    {"id": "KP21", "graph_type": "problem", "course_id": "C2026DS001", "name": "栈的定义与实现", "category": 2, "level": 3, "related_kp": 0, "error_rate": 0, "count": 0},
    {"id": "KP24", "graph_type": "problem", "course_id": "C2026DS001", "name": "栈的典型应用", "category": 2, "level": 3, "related_kp": 0, "error_rate": 0, "count": 0},
    {"id": "EC3", "graph_type": "problem", "course_id": "C2026DS001", "name": "错题簇：运算符优先级判断", "category": 3, "level": 4, "related_kp": 0, "error_rate": 0, "count": 14},
    {"id": "PB3", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何压缩一段文本？", "category": 0, "level": 1, "related_kp": 3, "error_rate": 31, "count": 0},
    {"id": "PB3-1", "graph_type": "problem", "course_id": "C2026DS001", "name": "如何构造最优前缀码？", "category": 1, "level": 2, "related_kp": 2, "error_rate": 35, "count": 0},
    {"id": "KP44", "graph_type": "problem", "course_id": "C2026DS001", "name": "哈夫曼树与编码", "category": 2, "level": 3, "related_kp": 0, "error_rate": 0, "count": 0},
    {"id": "EC4", "graph_type": "problem", "course_id": "C2026DS001", "name": "错题簇：WPL 计算失误", "category": 3, "level": 4, "related_kp": 0, "error_rate": 0, "count": 21},
    {"id": "G0", "graph_type": "goal", "course_id": "C2026DS001", "name": "具备数据结构建模与算法设计能力", "category": 0, "achieve": 68.9, "weight": 100},
    {"id": "G1", "graph_type": "goal", "course_id": "C2026DS001", "name": "掌握线性结构的组织与运算", "category": 1, "achieve": 86.4, "weight": 25},
    {"id": "G2", "graph_type": "goal", "course_id": "C2026DS001", "name": "掌握树形结构的构建与遍历", "category": 1, "achieve": 64.3, "weight": 30},
    {"id": "G3", "graph_type": "goal", "course_id": "C2026DS001", "name": "掌握图结构的表示与经典算法", "category": 1, "achieve": 55.8, "weight": 30},
    {"id": "G4", "graph_type": "goal", "course_id": "C2026DS001", "name": "具备算法效率分析能力", "category": 1, "achieve": 89.0, "weight": 15},
    {"id": "G1-1", "graph_type": "goal", "course_id": "C2026DS001", "name": "能实现顺序表与链表基本运算", "category": 2, "achieve": 90.0, "weight": 12},
    {"id": "G1-2", "graph_type": "goal", "course_id": "C2026DS001", "name": "能用栈/队列解决实际问题", "category": 2, "achieve": 81.5, "weight": 13},
    {"id": "G2-1", "graph_type": "goal", "course_id": "C2026DS001", "name": "能构建二叉树并实现三种遍历", "category": 2, "achieve": 66.0, "weight": 16},
    {"id": "G2-2", "graph_type": "goal", "course_id": "C2026DS001", "name": "能应用哈夫曼树解决编码问题", "category": 2, "achieve": 55.0, "weight": 8},
    {"id": "G2-3", "graph_type": "goal", "course_id": "C2026DS001", "name": "能完成树与森林的转换", "category": 2, "achieve": 0, "weight": 6},
    {"id": "G3-1", "graph_type": "goal", "course_id": "C2026DS001", "name": "能选择合适的图存储结构", "category": 2, "achieve": 63.0, "weight": 10},
    {"id": "G3-2", "graph_type": "goal", "course_id": "C2026DS001", "name": "能实现 DFS/BFS 并解决连通性问题", "category": 2, "achieve": 70.0, "weight": 10},
    {"id": "G3-3", "graph_type": "goal", "course_id": "C2026DS001", "name": "能应用最短路径与最小生成树算法", "category": 2, "achieve": 45.5, "weight": 10},
    {"id": "G4-1", "graph_type": "goal", "course_id": "C2026DS001", "name": "能推导算法时间/空间复杂度", "category": 2, "achieve": 89.0, "weight": 15},
]

# ============ 图谱边（公共数据） ============
MOCK_GRAPH_LINKS = []
for s, t, r in [
    ("KP01", "KP02", "pre"), ("KP02", "KP12", "pre"),
    ("KP11", "KP12", "pre"), ("KP11", "KP13", "pre"), ("KP13", "KP14", "advance"),
    ("KP12", "KP21", "pre"), ("KP13", "KP21", "pre"),
    ("KP21", "KP22", "parallel"), ("KP22", "KP23", "advance"), ("KP21", "KP24", "advance"),
    ("KP13", "KP31", "pre"), ("KP31", "KP32", "pre"), ("KP32", "KP33", "advance"),
    ("KP31", "KP34", "advance"), ("KP32", "KP44", "advance"),
    ("KP31", "KP41", "pre"), ("KP41", "KP42", "pre"), ("KP42", "KP43", "pre"),
    ("KP43", "KP51", "pre"), ("KP42", "KP52", "pre"), ("KP43", "KP52", "pre"),
    ("KP02", "KP52", "pre"), ("KP43", "KP53", "advance"),
    ("KP12", "KP61", "pre"), ("KP61", "KP62", "pre"), ("KP31", "KP63", "pre"),
    ("KP61", "KP64", "advance"), ("KP02", "KP71", "pre"), ("KP71", "KP72", "advance"),
    ("KP31", "KP73", "pre"),
]:
    MOCK_GRAPH_LINKS.append({"graph_type": "knowledge", "course_id": "C2026DS001", "source": s, "target": t, "relation": r})
for s, t, r in [
    ("PB1", "PB1-1", "split"), ("PB1", "PB1-2", "split"), ("PB1", "PB1-3", "split"),
    ("PB1-1", "KP41", "map"), ("PB1-2", "KP42", "map"), ("PB1-3", "KP52", "map"),
    ("KP52", "EC1", "error"), ("KP42", "EC2", "error"),
    ("PB2", "PB2-1", "split"), ("PB2", "PB2-2", "split"),
    ("PB2-1", "KP24", "map"), ("PB2-2", "KP21", "map"), ("KP24", "EC3", "error"),
    ("PB3", "PB3-1", "split"), ("PB3-1", "KP44", "map"), ("KP44", "EC4", "error"),
]:
    MOCK_GRAPH_LINKS.append({"graph_type": "problem", "course_id": "C2026DS001", "source": s, "target": t, "relation": r})
for s, t, r in [
    ("G0", "G1", "support"), ("G0", "G2", "support"), ("G0", "G3", "support"), ("G0", "G4", "support"),
    ("G1", "G1-1", "support"), ("G1", "G1-2", "support"),
    ("G2", "G2-1", "support"), ("G2", "G2-2", "support"), ("G2", "G2-3", "support"),
    ("G3", "G3-1", "support"), ("G3", "G3-2", "support"), ("G3", "G3-3", "support"),
    ("G4", "G4-1", "support"),
]:
    MOCK_GRAPH_LINKS.append({"graph_type": "goal", "course_id": "C2026DS001", "source": s, "target": t, "relation": r})

# ============ 知识点详情（公共数据） ============
MOCK_KP_DETAIL = {
    "kp_id": "KP52", "course_id": "C2026DS001",
    "name": "最短路径 Dijkstra 算法", "chapter": "第5章 图",
    "difficulty": 5, "is_key": True, "hours": 6,
    "summary": "Dijkstra 算法用于求解带非负权值有向图中单源点到其余各顶点的最短路径，基于贪心策略与逐步松弛思想，时间复杂度 O(n²)。",
    "completion_rate": 55, "mastery_rate": 41, "class_avg_mastery": 68,
    "pre_kp": json.dumps([{"kpId": "KP42", "name": "图的存储结构", "mastery": 63}, {"kpId": "KP43", "name": "图的遍历", "mastery": 70}, {"kpId": "KP02", "name": "时间复杂度分析", "mastery": 88}], ensure_ascii=False),
    "post_kp": json.dumps([{"kpId": "KP54", "name": "Floyd 多源最短路径", "mastery": 0}], ensure_ascii=False),
    "resources": json.dumps([
        {"resId": "R201", "type": "video", "title": "Dijkstra 算法原理与手工模拟", "duration": "24:18", "progress": 30},
        {"resId": "R202", "type": "ppt", "title": "第5章 图（下）课堂课件", "pages": 42, "progress": 100},
        {"resId": "R203", "type": "doc", "title": "《数据结构（C语言版）》P188-P193", "pages": 6, "progress": 0},
        {"resId": "R204", "type": "video", "title": "易错点串讲：负权边为何失效", "duration": "08:45", "progress": 0},
    ], ensure_ascii=False),
    "question_count": 32, "wrong_count": 7,
    "related_problems": json.dumps(["如何为地图导航设计最优路线？"], ensure_ascii=False),
}

# ============ 资源（公共数据） ============
# 从 GraphNode 构建 name → kp_id 映射，供 Resource 自动填 kp_id
_KP_NAME_TO_ID = {n["name"]: n["id"] for n in MOCK_GRAPH_NODES if n.get("graph_type") == "knowledge"}

MOCK_RESOURCES = []
for res_id, type_, title, kp, duration, pages, source, views in [
    ("R101", "video", "第4章 树与二叉树 · 概念导入", "二叉树基本概念", "22:10", 0, "MOOC 课程录课", 1240),
    ("R102", "video", "二叉树的三种遍历（递归实现）", "二叉树的遍历", "31:25", 0, "MOOC 课程录课", 1102),
    ("R103", "video", "二叉树遍历的非递归实现", "二叉树的遍历", "26:40", 0, "MOOC 课程录课", 876),
    ("R104", "ppt", "第4章 树与二叉树 课堂课件", "第4章 树", "", 68, "课堂PPT", 1560),
    ("R105", "doc", "《数据结构（C语言版）》第6章", "第4章 树", "", 46, "教材文献", 980),
    ("R106", "quiz", "第4章 章节自测（20题）", "第4章 树", "", 0, "课程题库", 720),
    ("R107", "video", "Dijkstra 算法原理与手工模拟", "最短路径 Dijkstra", "24:18", 0, "MOOC 课程录课", 1024),
    ("R108", "video", "易错点串讲：负权边为何失效", "最短路径 Dijkstra", "08:45", 0, "补救微课", 340),
    ("R109", "ppt", "第5章 图（下）课堂课件", "第5章 图", "", 42, "课堂PPT", 1320),
    ("R110", "doc", "《算法导论》第24章 单源最短路径", "最短路径 Dijkstra", "", 32, "拓展文献", 456),
    ("R111", "quiz", "图论综合训练包（35题）", "第5章 图", "", 0, "课程题库", 610),
    ("R112", "video", "循环队列判空判满专题", "循环队列判空判满", "12:30", 0, "补救微课", 890),
]:
    _kp_id = _KP_NAME_TO_ID.get(kp, "")
    MOCK_RESOURCES.append({
        "res_id": res_id, "course_id": "C2026DS001", "title": title, "type": type_,
        "kp": kp, "kp_id": _kp_id,
        "category": "knowledge" if _kp_id else "other",
        "duration": duration, "pages": pages, "source": source, "views": views,
    })

# ============ 题库（公共数据） ============
MOCK_QUESTIONS = [
    {
        "q_id": "Q1024", "course_id": "C2026DS001", "kp_id": "KP52",
        "type": "single", "difficulty": 4, "score": 5, "status": "published",
        "stem": '在带权有向图中使用 Dijkstra 算法求单源最短路径，若图中存在权值为 <code>-2</code> 的边，则下列说法正确的是：',
        "options": json.dumps([{"key": "A", "text": "算法仍然正确，只是效率降低"}, {"key": "B", "text": "算法可能得到错误结果，应改用 Bellman-Ford 算法"}, {"key": "C", "text": "算法一定进入死循环"}, {"key": "D", "text": "只要不存在负权回路，Dijkstra 一定正确"}], ensure_ascii=False),
        "answer": "B", "analysis": "Dijkstra 依赖贪心假设，前提是所有边权非负。",
        "kp_path": json.dumps(["第5章 图", "图的最短路径", "最短路径 Dijkstra"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 52, "avg_seconds": 96, "error_type": "概念混淆",
    },
    {
        "q_id": "Q1025", "course_id": "C2026DS001", "kp_id": "KP31",
        "type": "single", "difficulty": 3, "score": 5, "status": "published",
        "stem": '一棵完全二叉树共有 <code>1000</code> 个结点，则该树中叶子结点的个数为：',
        "options": json.dumps([{"key": "A", "text": "499"}, {"key": "B", "text": "500"}, {"key": "C", "text": "501"}, {"key": "D", "text": "502"}], ensure_ascii=False),
        "answer": "B", "analysis": "完全二叉树中度为 1 的结点最多 1 个。",
        "kp_path": json.dumps(["第4章 树与二叉树", "二叉树的性质", "完全二叉树性质"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 68, "avg_seconds": 78, "error_type": "公式记忆错误",
    },
    {
        "q_id": "Q1026", "course_id": "C2026DS001", "kp_id": "KP23",
        "type": "single", "difficulty": 4, "score": 5, "status": "published",
        "stem": '容量为 <code>MAXSIZE</code> 的循环队列，采用"牺牲一个单元"方式区分队空与队满，则队满的条件是：',
        "options": json.dumps([{"key": "A", "text": "rear == front"}, {"key": "B", "text": "(rear + 1) % MAXSIZE == front"}, {"key": "C", "text": "rear - front == MAXSIZE"}, {"key": "D", "text": "(front + 1) % MAXSIZE == rear"}], ensure_ascii=False),
        "answer": "B", "analysis": "队满条件 (rear+1) % MAXSIZE == front。",
        "kp_path": json.dumps(["第3章 栈与队列", "队列的实现", "循环队列判空判满"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 61, "avg_seconds": 65, "error_type": "指针方向混淆",
    },
    # 补充更多用于 transaction 的题目
    {
        "q_id": "Q2001", "course_id": "C2026DS001", "kp_id": "KP01",
        "type": "single", "difficulty": 2, "score": 5, "status": "published",
        "stem": "下列关于时间复杂度的说法，正确的是：",
        "options": json.dumps([{"key": "A", "text": "时间复杂度是算法执行的精确秒数"}, {"key": "B", "text": "时间复杂度通常用渐进记号 O 表示上界"}, {"key": "C", "text": "O(n) 一定比 O(n²) 快"}, {"key": "D", "text": "时间复杂度与硬件性能有关"}], ensure_ascii=False),
        "answer": "B", "analysis": "渐进时间复杂度关注规模趋向无穷时的增长阶。",
        "kp_path": json.dumps(["第1章 绪论", "算法复杂度"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 0,
        "class_correct_rate": 75, "avg_seconds": 45, "error_type": "概念混淆",
    },
    {
        "q_id": "Q2002", "course_id": "C2026DS001", "kp_id": "KP02",
        "type": "single", "difficulty": 3, "score": 5, "status": "published",
        "stem": "以下函数的时间复杂度是：T(n) = T(n/2) + 1",
        "options": json.dumps([{"key": "A", "text": "O(n)"}, {"key": "B", "text": "O(log n)"}, {"key": "C", "text": "O(n log n)"}, {"key": "D", "text": "O(n²)"}], ensure_ascii=False),
        "answer": "B", "analysis": "每次规模减半，递归深度 log n。",
        "kp_path": json.dumps(["第1章 绪论", "时间复杂度分析"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 65, "avg_seconds": 55, "error_type": "公式记忆错误",
    },
    {
        "q_id": "Q2003", "course_id": "C2026DS001", "kp_id": "KP13",
        "type": "single", "difficulty": 2, "score": 5, "status": "published",
        "stem": "在单链表中，若要删除某给定指针 p 指向的结点（非尾结点），最少需要修改指针多少次？",
        "options": json.dumps([{"key": "A", "text": "1 次"}, {"key": "B", "text": "2 次"}, {"key": "C", "text": "3 次"}, {"key": "D", "text": "不确定"}], ensure_ascii=False),
        "answer": "B", "analysis": "至少需要修改前驱结点的 next 和当前结点的前驱。",
        "kp_path": json.dumps(["第2章 线性表", "单链表", "基本运算"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 0,
        "class_correct_rate": 70, "avg_seconds": 40, "error_type": "指针操作不清",
    },
    {
        "q_id": "Q2004", "course_id": "C2026DS001", "kp_id": "KP21",
        "type": "single", "difficulty": 2, "score": 5, "status": "published",
        "stem": "栈的特点是：",
        "options": json.dumps([{"key": "A", "text": "先进先出"}, {"key": "B", "text": "后进先出"}, {"key": "C", "text": "随机存取"}, {"key": "D", "text": "双端存取"}], ensure_ascii=False),
        "answer": "B", "analysis": "栈是后进先出 (LIFO) 的线性结构。",
        "kp_path": json.dumps(["第3章 栈与队列", "栈"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 0,
        "class_correct_rate": 90, "avg_seconds": 20, "error_type": "概念混淆",
    },
    {
        "q_id": "Q2005", "course_id": "C2026DS001", "kp_id": "KP32",
        "type": "single", "difficulty": 3, "score": 5, "status": "published",
        "stem": "对二叉树进行中序遍历，遍历顺序是：",
        "options": json.dumps([{"key": "A", "text": "根-左-右"}, {"key": "B", "text": "左-根-右"}, {"key": "C", "text": "左-右-根"}, {"key": "D", "text": "右-左-根"}], ensure_ascii=False),
        "answer": "B", "analysis": "中序遍历顺序：左子树 → 根 → 右子树。",
        "kp_path": json.dumps(["第4章 树与二叉树", "二叉树遍历"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 78, "avg_seconds": 35, "error_type": "遍历顺序混淆",
    },
    {
        "q_id": "Q2006", "course_id": "C2026DS001", "kp_id": "KP42",
        "type": "single", "difficulty": 3, "score": 5, "status": "published",
        "stem": "对于稀疏图（边数远少于顶点数平方），更适合使用的存储结构是：",
        "options": json.dumps([{"key": "A", "text": "邻接矩阵"}, {"key": "B", "text": "邻接表"}, {"key": "C", "text": "边集数组"}, {"key": "D", "text": "十字链表"}], ensure_ascii=False),
        "answer": "B", "analysis": "邻接表空间复杂度 O(n+e)，适合稀疏图。",
        "kp_path": json.dumps(["第5章 图", "图的存储结构"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 72, "avg_seconds": 50, "error_type": "概念混淆",
    },
    {
        "q_id": "Q2007", "course_id": "C2026DS001", "kp_id": "KP43",
        "type": "single", "difficulty": 3, "score": 5, "status": "published",
        "stem": "广度优先搜索 (BFS) 通常使用哪种数据结构辅助实现？",
        "options": json.dumps([{"key": "A", "text": "栈"}, {"key": "B", "text": "队列"}, {"key": "C", "text": "堆"}, {"key": "D", "text": "哈希表"}], ensure_ascii=False),
        "answer": "B", "analysis": "BFS 按层扩展，使用队列保证先进先出的扩展顺序。",
        "kp_path": json.dumps(["第5章 图", "图的遍历"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 80, "avg_seconds": 45, "error_type": "概念混淆",
    },
    {
        "q_id": "Q2008", "course_id": "C2026DS001", "kp_id": "KP44",
        "type": "single", "difficulty": 4, "score": 5, "status": "published",
        "stem": "哈夫曼编码中，若有 4 个字符频率分别为 1、3、5、7，则编码后 WPL 是：",
        "options": json.dumps([{"key": "A", "text": "17"}, {"key": "B", "text": "22"}, {"key": "C", "text": "24"}, {"key": "D", "text": "26"}], ensure_ascii=False),
        "answer": "C", "analysis": "合并 1+3=4, 4+5=9, 9+7=16, WPL = 1×3+3×3+5×2+7×1 = 24。",
        "kp_path": json.dumps(["第4章 树与二叉树", "哈夫曼树"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 55, "avg_seconds": 72, "error_type": "WPL 计算失误",
    },
    {
        "q_id": "Q2009", "course_id": "C2026DS001", "kp_id": "KP41",
        "type": "single", "difficulty": 1, "score": 5, "status": "published",
        "stem": "图的定义中，顶点集和边集分别满足什么条件？",
        "options": json.dumps([{"key": "A", "text": "顶点集非空，边集可为空"}, {"key": "B", "text": "顶点集可为空，边集非空"}, {"key": "C", "text": "两者都必须非空"}, {"key": "D", "text": "两者都可以为空"}], ensure_ascii=False),
        "answer": "A", "analysis": "图的定义：V 非空，E 可以为空（平凡图）。",
        "kp_path": json.dumps(["第5章 图", "图的定义与术语"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 0,
        "class_correct_rate": 85, "avg_seconds": 25, "error_type": "定义记忆错误",
    },
    {
        "q_id": "Q2010", "course_id": "C2026DS001", "kp_id": "KP51",
        "type": "single", "difficulty": 4, "score": 5, "status": "published",
        "stem": "Kruskal 算法求最小生成树的时间复杂度是：",
        "options": json.dumps([{"key": "A", "text": "O(n²)"}, {"key": "B", "text": "O(e log e)"}, {"key": "C", "text": "O(n e)"}, {"key": "D", "text": "O(n log n)"}], ensure_ascii=False),
        "answer": "B", "analysis": "Kruskal 需对边排序 O(e log e)，并查集操作近似 O(α(e))。",
        "kp_path": json.dumps(["第5章 图", "最小生成树"], ensure_ascii=False),
        "pre_kp": "[]", "post_kp": "[]", "is_key": 1,
        "class_correct_rate": 58, "avg_seconds": 68, "error_type": "算法复杂度混淆",
    },
]

# ============ 干预（公共数据） ============
MOCK_INTERVENTIONS = [
    {
        "iv_id": "IV20260828001", "class_id": "CL2301", "status": "pending", "level": "danger", "scope": "common",
        "title": "针对班级共性薄弱点「最短路径 Dijkstra」的集体干预",
        "target": "计算机 2301 班 · 12 名掌握率低于 60% 的学生",
        "reason": "AI 归因：42% 概率为前置知识缺失，31% 概率为算法流程未内化。",
        "steps_json": json.dumps(["课堂插入 10 分钟集体手工模拟", "推送补救微课", "布置过渡题", "3 日后复测"], ensure_ascii=False),
        "expect_effect": "预计掌握率由 50.3% 提升至 68%~72%",
    },
    {
        "iv_id": "IV20260828002", "class_id": "CL2301", "status": "pending", "level": "danger", "scope": "individual",
        "title": "赵梓涵 · 全面滞后个体干预",
        "target": "赵梓涵 · 滞后 12 学时，3 日未登录",
        "reason": "AI 归因：学习行为中断为主因。",
        "steps_json": json.dumps(["联系学生", "重规划路径", "设置微目标", "连续打卡恢复"], ensure_ascii=False),
        "expect_effect": "预计 2 周内进度追平至滞后 ≤ 4 学时",
    },
]

# ============ 模板（公共数据） ============
MOCK_TEMPLATES = [
    {"tpl_id": "TPL001", "name": "前置知识缺失补齐三步法", "scene": "前置知识缺失", "steps_json": "[]", "resources_json": "[]"},
    {"tpl_id": "TPL002", "name": "程序性知识填表强化法", "scene": "算法流程不清", "steps_json": "[]", "resources_json": "[]"},
    {"tpl_id": "TPL003", "name": "难度阶梯重构法", "scene": "难度梯度过陡", "steps_json": "[]", "resources_json": "[]"},
]

# ============ 报告（公共数据） ============
MOCK_REPORTS = [
    {
        "report_id": "RP20260828001", "class_id": "CL2301", "status": "ready",
        "title": "计算机 2301 班 · 第5章「图」阶段学情分析报告",
        "detail_json": json.dumps({
            "reportId": "RP20260828001",
            "title": "计算机 2301 班 · 第5章「图」阶段学情分析报告",
            "sections": [
                {"title": "一、整体掌握度", "paragraphs": ["本阶段班级平均掌握率 76.1%。"],
                 "bullets": ["达标知识点 2 个", "待加强 2 个", "薄弱 2 个"]},
                {"title": "二、共性短板与归因", "paragraphs": ["识别出 4 类主要成因。"],
                 "bullets": ["前置知识缺失 42%", "算法流程未内化 31%"]},
            ],
        }, ensure_ascii=False),
    },
]

# ============ 学生档位配置 ============
# 只保留「档位」，用于决定该生生成多少答题记录 / 练习会话 / 答疑会话。
# 学习路径不再由 seed 生成（历史上那套手写模板与图谱不一致），
# 改由图谱派生：见 services/learning_path.py 与 bootstrap.ensure_learning_paths()。
STUDENT_PROFILES = {
    "S20260317": {"tier": "custom_chen"},   # 陈思远
    # 优秀：王志豪 / 刘欣然 / 何子轩
    "S20260319": {"tier": "excellent"},
    "S20260325": {"tier": "excellent"},
    "S20260328": {"tier": "excellent"},
    # 良好：孙博文 / 陈欣怡 / 李雅琪 / 周雨桐
    "S20260330": {"tier": "good"},
    "S20260318": {"tier": "good"},
    "S20260321": {"tier": "good"},
    "S20260329": {"tier": "good"},
    # 合格：林浩然 / 吴嘉豪
    "S20260341": {"tier": "medium"},
    "S20260333": {"tier": "medium"},
    # 薄弱：赵梓涵 / 徐子墨
    "S20260322": {"tier": "weak"},
    "S20260337": {"tier": "weak"},
}


# ============ AnswerRecord 生成 ============
ERROR_TYPES = ["概念混淆", "公式记忆错误", "算法流程不清", "计算失误", "指针操作不清",
               "遍历顺序混淆", "WPL 计算失误", "复杂度混淆", "定义记忆错误"]


def _gen_answer_records():
    """为每个学生生成 15-25 条答题记录"""
    records = []
    q_ids = ["Q1024", "Q1025", "Q1026", "Q2001", "Q2002", "Q2003",
             "Q2004", "Q2005", "Q2006", "Q2007", "Q2008", "Q2009", "Q2010"]
    # q_id -> (kp_id, correct_answer)
    q_meta = {
        "Q1024": ("KP52", "B"), "Q1025": ("KP31", "B"), "Q1026": ("KP23", "B"),
        "Q2001": ("KP01", "B"), "Q2002": ("KP02", "B"), "Q2003": ("KP13", "B"),
        "Q2004": ("KP21", "B"), "Q2005": ("KP32", "B"), "Q2006": ("KP42", "B"),
        "Q2007": ("KP43", "B"), "Q2008": ("KP44", "C"), "Q2009": ("KP41", "A"),
        "Q2010": ("KP51", "B"),
    }
    wrong_choices_by_q = {
        "Q1024": ["A", "C", "D"], "Q1025": ["A", "C", "D"], "Q1026": ["A", "C", "D"],
        "Q2001": ["A", "C", "D"], "Q2002": ["A", "C", "D"], "Q2003": ["A", "C", "D"],
        "Q2004": ["A", "C", "D"], "Q2005": ["A", "C", "D"], "Q2006": ["A", "C", "D"],
        "Q2007": ["A", "C", "D"], "Q2008": ["A", "B", "D"], "Q2009": ["B", "C", "D"],
        "Q2010": ["A", "C", "D"],
    }
    letter_choices = ["A", "B", "C", "D"]

    for acct in STUDENT_ACCOUNTS:
        uid = acct["user_id"]
        profile = STUDENT_PROFILES.get(uid, {})
        tier = profile.get("tier", "good")

        # 决定答题数量
        if tier == "custom_chen":
            total = 24
        elif tier == "excellent":
            total = 22
        elif tier == "good":
            total = 20
        elif tier == "medium":
            total = 18
        else:
            total = 16

        # 决定正确率
        if tier == "custom_chen":
            correct_rate = 0.68
        elif tier == "excellent":
            correct_rate = 0.85
        elif tier == "good":
            correct_rate = 0.72
        elif tier == "medium":
            correct_rate = 0.55
        else:
            correct_rate = 0.42

        correct_letter = correct_rate

        # 生成时间分布：最近 12 天每天 1-3 条（保证 streak 可算）
        # 今天（0 天前）陈思远特殊：4 条，其他学生今天 1-2 条
        if tier == "custom_chen":
            today_count = 4
            extra_today_seconds = [180, 900, 720, 1080]  # 合计 2880 秒 = 48 分钟
        else:
            today_count = random.randint(1, 2)
            extra_today_seconds = None

        # 确保过去 12 天每天至少 1 条（保证 streak 至少 12）
        # 陈思远：过去 11 天每天至少 1 条（今天=day 0 已保证 4 条）
        # 其他学生：过去 11 天每天至少 1 条（今天也有 1-2 条）
        all_times = []
        for day in range(12):
            if day == 0:
                # 今天
                count = today_count
            else:
                # 过去 11 天：至少 1 条，其余随机分配
                remaining_extra = (total - today_count) - 11  # 剩余多出来的
                count = 1 + max(0, remaining_extra // 11)
                if remaining_extra > 0 and random.random() < 0.3:
                    count += 1  # 30% 概率多一条
                count = min(count, 4)  # 每天不超过 4 条
                count = max(count, 1)  # 每天至少 1 条

            for i in range(count):
                if day == 0 and tier == "custom_chen" and extra_today_seconds:
                    # 陈思远今天 4 条，硬编码时间点保证都在 BASE 之前
                    chen_today_times = [
                        BASE.replace(hour=14, minute=10),
                        BASE.replace(hour=15, minute=30),
                        BASE.replace(hour=16, minute=15),
                        BASE.replace(hour=16, minute=45),
                    ]
                    all_times.append((0, chen_today_times[i]))
                elif day == 0:
                    all_times.append((0, BASE.replace(
                        hour=random.randint(9, 16), minute=random.randint(0, 59))))
                else:
                    all_times.append((day, days_ago(day, hour_jitter=5)))

        # 按时间排序（所有答题记录按时间先后）
        all_times.sort(key=lambda x: x[1])

        session_counter = 1
        session_size = random.randint(4, 6)
        session_id = f"PS{uid}{session_counter:02d}"
        sess_count = 0
        chen_today_idx = 0  # 陈思远今天答题时间分配索引

        for idx, (days_back, created_at) in enumerate(all_times):
            if sess_count >= session_size:
                session_counter += 1
                session_size = random.randint(4, 6)
                session_id = f"PS{uid}{session_counter:02d}"
                sess_count = 0

            qid = random.choice(q_ids)
            kp_id, corr = q_meta[qid]
            is_correct = 1 if random.random() < correct_letter else 0
            my_ans = corr if is_correct else random.choice(wrong_choices_by_q[qid])
            duration = random.randint(30, 120) if is_correct else random.randint(60, 180)
            # 陈思远今天的答题时长用预设值
            if tier == "custom_chen" and days_back == 0 and extra_today_seconds:
                if chen_today_idx < len(extra_today_seconds):
                    duration = extra_today_seconds[chen_today_idx]
                    chen_today_idx += 1

            error_type = "" if is_correct else random.choice(ERROR_TYPES)

            records.append({
                "session_id": session_id,
                "user_id": uid,
                "q_id": qid,
                "kp_id": kp_id,
                "my_answer": my_ans,
                "correct_answer": corr,
                "is_correct": is_correct,
                "duration_seconds": duration,
                "error_type": error_type,
                "created_at": created_at,
            })
            sess_count += 1

    return records


MOCK_ANSWER_RECORDS = _gen_answer_records()


# ============ PracticeSession 生成 ============
def _gen_practice_sessions():
    """每学生 2-4 条 PracticeSession"""
    sessions = []
    modes = ["weak", "order", "random"]

    for acct in STUDENT_ACCOUNTS:
        uid = acct["user_id"]
        profile = STUDENT_PROFILES.get(uid, {})
        tier = profile.get("tier", "good")

        # 决定 session 数量
        if tier == "custom_chen":
            count = 4
        elif tier == "excellent":
            count = 4
        elif tier == "good":
            count = 3
        elif tier == "medium":
            count = 3
        else:
            count = 2

        # 计算该学生的答题记录里有哪些 session
        user_records = [r for r in MOCK_ANSWER_RECORDS if r["user_id"] == uid]
        record_sessions = sorted(set(r["session_id"] for r in user_records))

        # 时间分布
        session_times = []
        if tier == "custom_chen":
            # 陈思远特殊：今天 1 条长 session (48 分钟=2880秒)，过去 11 天每天 1 条短的
            session_times.append((0, 2880, "今天 14:00 - 14:48"))
            for day in range(1, 12):
                session_times.append((day, random.randint(600, 1200), f"过去{day}天"))
        else:
            for day in range(count):
                session_times.append((day, random.randint(600, 1800), ""))

        for i, (days_back, duration, label) in enumerate(session_times[:count]):
            mode = random.choice(modes)
            session_id = record_sessions[i] if i < len(record_sessions) else f"PS{uid}{i+1:02d}"

            created_at = days_ago(days_back, hour_jitter=4) if days_back > 0 else BASE.replace(
                hour=random.randint(9, 20), minute=random.randint(0, 59))
            finished_at = created_at + timedelta(seconds=duration)

            # 从该 session 的答题记录计算 correct/wrong/total
            sess_records = [r for r in user_records if r["session_id"] == session_id]
            total = len(sess_records) if sess_records else random.randint(6, 12)
            if sess_records:
                correct = sum(1 for r in sess_records if r["is_correct"])
            else:
                if tier == "excellent":
                    correct = random.randint(total - 1, total)
                elif tier == "custom_chen":
                    correct = int(total * 0.68)
                elif tier == "good":
                    correct = int(total * 0.72)
                elif tier == "medium":
                    correct = int(total * 0.55)
                else:
                    correct = int(total * 0.42)
            wrong = total - correct
            accuracy = round(correct / total * 100, 1) if total > 0 else 0

            sessions.append({
                "session_id": session_id,
                "user_id": uid,
                "mode": mode,
                "total": total,
                "correct": correct,
                "wrong": wrong,
                "accuracy": accuracy,
                "duration_seconds": duration,
                "status": "finished",
                "created_at": created_at,
                "finished_at": finished_at,
                "questions_snapshot": "[]",
            })

    return sessions


MOCK_PRACTICE_SESSIONS = _gen_practice_sessions()


# ============ ChatSession + ChatMessage 生成 ============
CHAT_TOPICS = [
    ("为什么 Dijkstra 算法不能处理负权边？", "最短路径 Dijkstra"),
    ("哈夫曼编码的构造步骤是怎样的？", "哈夫曼树与编码"),
    ("二叉树的前序、中序、后序遍历有什么本质区别？", "二叉树的遍历"),
    ("如何选择图的存储结构？邻接矩阵和邻接表各有什么优劣？", "图的存储结构"),
    ("循环队列为什么要牺牲一个存储单元？", "循环队列判空判满"),
    ("快排最坏情况是什么时候？", "快速排序"),
    ("Kruskal 和 Prim 求最小生成树有什么区别？", "最小生成树"),
    ("BFS 和 DFS 分别适合解决什么问题？", "图的遍历 DFS/BFS"),
]


def _gen_chat_data():
    """为每个学生生成 ChatSession + ChatMessage"""
    sessions = []
    messages = []
    msg_id = 1

    for acct in STUDENT_ACCOUNTS:
        uid = acct["user_id"]
        profile = STUDENT_PROFILES.get(uid, {})
        tier = profile.get("tier", "good")

        # session 数量
        if tier == "custom_chen":
            session_infos = [
                ("Dijkstra 算法为什么不能处理负权边？", "最短路径 Dijkstra", 6),
                ("哈夫曼编码的构造步骤", "哈夫曼树与编码", 4),
            ]
        elif tier == "excellent":
            session_infos = [
                (*random.choice(CHAT_TOPICS), random.randint(4, 7)) for _ in range(3)
            ]
        elif tier == "good":
            session_infos = [
                (*random.choice(CHAT_TOPICS), random.randint(3, 6)) for _ in range(2)
            ]
        elif tier == "medium":
            session_infos = [
                (*random.choice(CHAT_TOPICS), random.randint(3, 5)) for _ in range(2)
            ]
        else:
            session_infos = [
                (*random.choice(CHAT_TOPICS), random.randint(2, 4)) for _ in range(1)
            ]

        for s_idx, (title, kp_name, rounds) in enumerate(session_infos):
            session_id = f"CH{uid}{s_idx+1:02d}"
            created_at = days_ago(random.randint(0, 7), hour_jitter=3)
            updated_at = created_at + timedelta(minutes=rounds * 2)

            sessions.append({
                "session_id": session_id,
                "user_id": uid,
                "title": title,
                "kp_name": kp_name,
                "rounds": rounds,
                "created_at": created_at,
                "updated_at": updated_at,
            })

            # 生成消息对 (user, assistant)，最后多一条 assistant
            methods = ["guided", "socratic", "step_by_step"]
            for r in range(rounds):
                user_time = created_at + timedelta(minutes=r * 2)
                ai_time = created_at + timedelta(minutes=r * 2 + 1)
                time_str_u = user_time.strftime("%H:%M")
                time_str_a = ai_time.strftime("%H:%M")

                # user 消息
                messages.append({
                    "id": msg_id, "session_id": session_id, "role": "me",
                    "method": "", "content": _user_msg_content(title, r),
                    "citations": "[]", "time_str": time_str_u,
                    "created_at": user_time,
                })
                msg_id += 1

                # assistant 消息
                messages.append({
                    "id": msg_id, "session_id": session_id, "role": "ai",
                    "method": random.choice(methods),
                    "content": _ai_msg_content(title, kp_name, r),
                    "citations": _citations_for_kp(kp_name),
                    "time_str": time_str_a,
                    "created_at": ai_time,
                })
                msg_id += 1

    return sessions, messages


def _user_msg_content(title, round_idx):
    """生成模拟的用户提问内容"""
    base = title.replace("？", "").replace("?", "")
    variants = [
        f"老师，我想请教一下：{base}？",
        f"这个问题我不太理解，{base}能详细讲讲吗？",
        f"关于{base}，我自己理解了一下但还是有点模糊。",
        f"{base}，我试试说一下我的思路...",
        f"好的我明白一部分了，那接下来呢？",
        f"我再想想，那如果换一种情况呢？",
    ]
    return f"<p>{variants[round_idx % len(variants)]}</p>"


def _ai_msg_content(title, kp_name, round_idx):
    """生成模拟的 AI 回复内容"""
    intros = [
        f"<p>同学好，关于「{kp_name}」这个问题，我们来一步步分析。</p>",
        f"<p>好的，我来引导你理解「{kp_name}」。</p>",
        f"<p>这个问题的关键在于理解核心思想，让我用一个小例子来说明：</p>",
        f"<p>很好的思考角度！让我补充几个要点来帮你完善这个思路。</p>",
    ]
    bodies = [
        f"<p><strong>核心要点：</strong>1）{kp_name}的基本思想是... 2）关键步骤包括... 3）常见的误区有...</p>",
        f"<p>让我画一个简图来帮助你理解。<br>假设顶点V0到其他顶点的距离...</p>",
        f"<p>总结一下：你需要牢记三个前提条件和两个边界情况，这样考试中的这类题基本就能拿下了。</p>",
        f"<p>太棒了！你已经掌握了核心概念。如果想进一步加深，可以看看教材中的相关例题。</p>",
    ]
    return intros[round_idx % len(intros)] + bodies[round_idx % len(bodies)]


def _citations_for_kp(kp_name):
    """为指定知识点生成模拟的引用"""
    kp_citations = {
        "最短路径 Dijkstra": [{"source": "第5章 图（下）课堂课件", "locator": "P28", "quote": "若图中所有边的权值均为非负值...", "kp": "KP52"}],
        "哈夫曼树与编码": [{"source": "《数据结构（C语言版）》", "locator": "P232", "quote": "哈夫曼树是带权路径长度最小的二叉树...", "kp": "KP44"}],
        "二叉树的遍历": [{"source": "第4章 树与二叉树 课堂课件", "locator": "P45", "quote": "遍历顺序：左子树 → 根 → 右子树...", "kp": "KP32"}],
        "图的存储结构": [{"source": "算法导论第22章", "locator": "P540", "quote": "邻接表适合稀疏图...", "kp": "KP42"}],
        "循环队列判空判满": [{"source": "《数据结构（C语言版）》", "locator": "P85", "quote": "牺牲一个单元区分队空与队满...", "kp": "KP23"}],
        "快速排序": [{"source": "第7章 排序 课堂课件", "locator": "P32", "quote": "最坏情况发生在每次选到极值作为基准...", "kp": "KP72"}],
        "最小生成树": [{"source": "算法导论第23章", "locator": "P568", "quote": "Kruskal贪心选边，Prim贪心加点...", "kp": "KP51"}],
        "图的遍历 DFS/BFS": [{"source": "第5章 图 课堂课件", "locator": "P20", "quote": "BFS使用队列，DFS使用栈/递归...", "kp": "KP43"}],
    }
    cites = kp_citations.get(kp_name, [{"source": "课程教材", "locator": "相关页面", "quote": "请查阅对应章节...", "kp": ""}])
    return json.dumps(cites, ensure_ascii=False)


MOCK_CHAT_SESSIONS, MOCK_CHAT_MESSAGES = _gen_chat_data()


# ============ Dashboard 聚合数据（仅保留班级级，个人快照全部删除） ============
# 每个元素: (data_type, class_id, data_key, python_dict)
DASHBOARD_DATA = []

# --- intervention_effect ---
_intervention_effect = {
    "ivId": "IV20260828001",
    "xAxis": ["干预前3日", "干预前1日", "干预日", "干预后1日", "干预后3日", "干预后7日"],
    "series": [
        {"name": "干预组掌握率", "data": [50.2, 52.0, 52.0, 61.5, 68.3, 71.4], "color": "#22c55e"},
        {"name": "对照组掌握率", "data": [51.0, 51.8, 52.2, 53.4, 55.1, 56.8], "color": "#64748b"},
    ],
    "summary": "干预组 7 日内掌握率提升 19.4 个百分点，对照组仅提升 5.8 个百分点。",
}
DASHBOARD_DATA.append(("intervention_effect", "", "", _intervention_effect))

# --- strategy_templates ---
_strategy_templates = [
    {"tplId": "TPL001", "name": "前置知识缺失补齐三步法", "scene": "前置知识缺失", "useCount": 24, "successRate": 82, "avgLift": 15.6},
    {"tplId": "TPL002", "name": "程序性知识填表强化法", "scene": "算法流程不清", "useCount": 18, "successRate": 78, "avgLift": 13.2},
    {"tplId": "TPL003", "name": "难度阶梯重构法", "scene": "难度梯度过陡", "useCount": 12, "successRate": 75, "avgLift": 11.8},
    {"tplId": "TPL004", "name": "学习中断唤醒法", "scene": "学习行为中断", "useCount": 9, "successRate": 67, "avgLift": 22.4},
    {"tplId": "TPL005", "name": "错题簇集中歼灭法", "scene": "错题集中", "useCount": 21, "successRate": 85, "avgLift": 17.1},
]
DASHBOARD_DATA.append(("strategy_templates", "", "", _strategy_templates))

# --- report_detail ---
_report_detail = {
    "reportId": "RP20260828001",
    "title": "计算机 2301 班 · 第5章「图」阶段学情分析报告",
    "sections": [
        {"title": "一、整体掌握度", "paragraphs": ["本阶段班级共覆盖 6 个知识点，平均掌握率 59.8%。"],
         "bullets": ["达标知识点 1 个", "待加强 3 个", "薄弱 2 个"]},
        {"title": "二、共性短板与归因", "paragraphs": ["系统识别出 4 类主要成因。"],
         "bullets": ["前置知识缺失 42%", "算法流程未内化 31%", "难度梯度过陡 18%", "练习量不足 9%"]},
        {"title": "三、个体预警情况", "paragraphs": ["本阶段共触发 16 条预警，涉及 7 名学生。"],
         "bullets": ["红色 5 条：陈思远、赵梓涵、徐子墨、吴嘉豪", "黄色 11 条：其他 4 名临界学生"]},
        {"title": "四、下阶段教学建议", "paragraphs": [],
         "bullets": ["课堂 5 分钟对比表 + 10 分钟手工模拟", "AI 补充 10 道 2-3 星过渡题", "确认执行 Dijkstra 集体干预"]},
    ],
}
DASHBOARD_DATA.append(("report_detail", "", "", _report_detail))

# --- gen_config / generated_questions（AI 出题相关，保留） ---
_gen_config = {
    "materials": [
        {"fileId": "M001", "name": "第5章 图（下）课堂课件.pptx", "size": "8.4 MB", "type": "ppt", "status": "parsed", "kpCount": 6},
        {"fileId": "M002", "name": "数据结构（C语言版）第7章.pdf", "size": "12.1 MB", "type": "doc", "status": "parsed", "kpCount": 9},
        {"fileId": "M003", "name": "Dijkstra 算法原理与手工模拟.mp4", "size": "186 MB", "type": "video", "status": "parsing", "kpCount": 0, "progress": 62},
    ],
    "kpOptions": [
        {"kpId": "KP41", "name": "图的定义与术语"},
        {"kpId": "KP42", "name": "图的存储结构"},
        {"kpId": "KP43", "name": "图的遍历 DFS/BFS"},
        {"kpId": "KP51", "name": "最小生成树"},
        {"kpId": "KP52", "name": "最短路径 Dijkstra"},
    ],
    "typeOptions": [
        {"key": "single", "name": "单选题"}, {"key": "multi", "name": "多选题"},
        {"key": "judge", "name": "判断题"}, {"key": "blank", "name": "填空题"},
        {"key": "code", "name": "算法设计题"},
    ],
}
DASHBOARD_DATA.append(("gen_config", "", "", _gen_config))

_generated_questions = [
    {
        "qId": "GQ001", "type": "single", "difficulty": 3, "status": "pending",
        "stem": "在含 n 个顶点、e 条边的稀疏有向图中，若要频繁遍历某顶点的所有出边，则最合适的存储结构是：",
        "options": [{"key": "A", "text": "邻接矩阵"}, {"key": "B", "text": "邻接表", "right": True}, {"key": "C", "text": "边集数组"}, {"key": "D", "text": "十字链表"}],
        "analysis": "稀疏图使用邻接矩阵会造成 O(n²) 空间浪费；邻接表按顶点组织出边链，遍历时间为 O(出度)。",
        "kpPath": ["第5章 图", "图的存储结构", "邻接表"],
        "kpId": "KP42", "preKp": ["图的定义与术语"], "postKp": ["图的遍历 DFS/BFS"], "isKey": True,
        "sourceRef": {"fileId": "M001", "locator": "P12 · 存储结构对比表"},
        "estimatedCorrectRate": 72,
    },
    {
        "qId": "GQ002", "type": "single", "difficulty": 4, "status": "pending",
        "stem": "对下图执行 Dijkstra 算法（源点 V0），第 2 轮主循环结束后被并入集合 S 的顶点是：V0→V1:4  V0→V2:1  V2→V1:2  V1→V3:5  V2→V3:8",
        "options": [{"key": "A", "text": "V1"}, {"key": "B", "text": "V2"}, {"key": "C", "text": "V1（dist=3，经 V2 松弛后）", "right": True}, {"key": "D", "text": "V3"}],
        "analysis": "第 1 轮选 V2（dist=1）并入 S，松弛得 dist[V1]=3。第 2 轮剩余顶点中 dist 最小者为 V1。",
        "kpPath": ["第5章 图", "图的最短路径", "最短路径 Dijkstra"],
        "kpId": "KP52", "preKp": ["图的存储结构", "图的遍历"], "isKey": True,
        "sourceRef": {"fileId": "M002", "locator": "P188"},
        "estimatedCorrectRate": 45,
    },
]
DASHBOARD_DATA.append(("generated_questions", "", "", _generated_questions))
