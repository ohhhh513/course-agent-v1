"""[已退役] 从 after_class.json 导入课后题库到 questions 表。

退役原因
--------
原实现依赖「王道小节前缀 → KP」映射（`backend/kp_section_mapping.json`）与旧课程
`C2026DS001`、旧 KP 编号（KP01/KP11/…）。课程结构已全量替换为
「章 CH01-09 + 知识点 KP001-026」（见 `docs/主库数据规范.md`），该映射文件已删除，
本脚本的前提不复存在。

当前正式题库的唯一产生方式是平台操作：
    教师建课 → 课程结构与图谱编排（章 / 知识点）→ 前端录题 或 AI 出题后发布
批量导入请走教师端题库上传接口并按主库规范提供 chapter_id / kp_id。

保留本文件仅作为退役说明，执行不会做任何写入。
"""
import sys

MESSAGE = (
    "[已退役] import_st_bank.py 不再从 after_class.json 导入题库。\n"
    "题库请由平台产生：教师建课 → 图谱编排（章 CH0x / 知识点 KP0xx）→ 录题或 AI 出题发布。\n"
    "详见 docs/主库数据规范.md"
)


def main() -> int:
    print(MESSAGE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
