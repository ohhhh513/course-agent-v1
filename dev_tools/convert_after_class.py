"""
将 v1.0 after_class.json 转为当前 /question/import 契约，并挂上 KP 名称。

用法（项目根）:
  python dev_tools/convert_after_class.py

输出:
  dev_tools/questions_after_class_import.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(
    r"D:\all_contest\2026_9_4_course-agent\course-agent-v1.0\backend\app\data\st\st_bank\after_class.json"
)
OUT = Path(__file__).resolve().parent / "questions_after_class_import.json"

# 王道小节前缀 → (章名, KP 名列表, 难度)
# KP 名与 course_structure_ds.json 一致
SECTION_MAP = [
    ("1.1", "第1章 绪论", ["数据结构概述"], 2),
    ("1.2", "第1章 绪论", ["算法与算法评价"], 3),
    ("2.2", "第2章 线性表", ["线性表", "顺序表"], 3),
    ("2.3", "第2章 线性表", ["线性表", "链表"], 3),
    ("3.1", "第3章 栈和队列", ["栈"], 3),
    ("3.2", "第3章 栈和队列", ["队列"], 3),
    ("3.3", "第3章 栈和队列", ["栈与队列的应用"], 4),
    ("3.4", "第5章 数组和广义表", ["多维数组与矩阵"], 3),
    ("4.", "第4章 串", ["串", "串的模式匹配"], 4),
    ("5.1", "第6章 树和二叉树", ["树与二叉树"], 2),
    ("5.2", "第6章 树和二叉树", ["树与二叉树"], 3),
    ("5.3", "第6章 树和二叉树", ["二叉树遍历"], 4),
    ("5.4", "第6章 树和二叉树", ["树与二叉树"], 3),
    ("5.5", "第6章 树和二叉树", ["树的应用"], 4),
    ("6.1", "第7章 图", ["图的存储与遍历"], 3),
    ("6.2", "第7章 图", ["图的存储与遍历"], 3),
    ("6.3", "第7章 图", ["图的存储与遍历"], 4),
    ("6.4", "第7章 图", ["最短路径与生成树", "拓扑与关键路径"], 4),
    ("7.2", "第8章 查找", ["查找"], 3),
    ("7.3", "第8章 查找", ["树形查找"], 4),
    ("7.4", "第8章 查找", ["树形查找"], 4),
    ("7.5", "第8章 查找", ["哈希表"], 3),
    ("8.2", "第9章 排序", ["插入排序"], 3),
    ("8.3", "第9章 排序", ["交换排序"], 3),
    ("8.4", "第9章 排序", ["选择排序"], 3),
    ("8.5", "第9章 排序", ["归并排序", "排序算法概述"], 3),
]


def map_section(chapter: str):
    text = str(chapter or "")
    for prefix, ch_name, kps, diff in SECTION_MAP:
        if text.startswith(prefix):
            return ch_name, kps, diff
    # 兜底：按章号首字符粗映射
    if text.startswith("1"):
        return "第1章 绪论", ["数据结构概述"], 3
    if text.startswith("2"):
        return "第2章 线性表", ["线性表"], 3
    if text.startswith("3"):
        return "第3章 栈和队列", ["栈"], 3
    if text.startswith("4"):
        return "第4章 串", ["串的模式匹配"], 3
    if text.startswith("5"):
        return "第6章 树和二叉树", ["树与二叉树"], 3
    if text.startswith("6"):
        return "第7章 图", ["图的存储与遍历"], 3
    if text.startswith("7"):
        return "第8章 查找", ["查找"], 3
    if text.startswith("8"):
        return "第9章 排序", ["排序算法概述"], 3
    return None


def convert_options(opt_dict, answer: str):
    order = [k for k in ("A", "B", "C", "D", "E", "F", "G", "H") if k in (opt_dict or {})]
    if not order and isinstance(opt_dict, dict):
        order = list(opt_dict.keys())
    ans = str(answer or "").strip()
    return [
        {"key": k, "text": str((opt_dict or {}).get(k, "")), "right": k in ans}
        for k in order
    ]


def main():
    if not SRC.is_file():
        raise SystemExit(f"源文件不存在: {SRC}")
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    out = []
    skipped = 0
    for item in raw:
        mapped = map_section(item.get("chapter"))
        if not mapped:
            skipped += 1
            continue
        chapter, kp_names, diff = mapped
        options = convert_options(item.get("options"), item.get("answer"))
        q = {
            "stem": (item.get("question") or "").strip(),
            "type": "single",
            "difficulty": diff,
            "score": 5,
            "status": "published",
            "options": options,
            "answer": str(item.get("answer") or "").strip(),
            "analysis": item.get("analysis") or "",
            "chapter": chapter,
            "kpNames": kp_names,
            "kp_path": [chapter] + kp_names,
            "is_key": 0,
            "sourceId": item.get("id"),
        }
        fig = {}
        if item.get("graph"):
            fig["graph"] = item["graph"]
        if item.get("options_graph"):
            fig["options_graph"] = item["options_graph"]
        has_image = bool(item.get("has_image"))
        if has_image or fig:
            fig["has_image"] = has_image
            q["figure_json"] = fig
            q["has_image"] = has_image
        if not q["stem"]:
            skipped += 1
            continue
        out.append(q)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with_fig = sum(1 for x in out if x.get("figure_json"))
    print(f"[done] 写入 {OUT}")
    print(f"  题目 {len(out)} 条（跳过 {skipped}）· 图题 {with_fig}")
    print(f"  契约字段: stem/options/answer/analysis/chapter/kpNames/figure_json/status")


if __name__ == "__main__":
    main()
