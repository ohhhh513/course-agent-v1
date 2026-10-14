"""填空题判分与导入预览。不连接真实数据库。"""
from unittest.mock import MagicMock

from app.services.blank_questions import grade_submission, pack_blank, student_view
from app.services.question_preview import preview_questions


def test_pack_and_grade_two_blanks():
    packed = pack_blank(
        "队列遵循____原则，栈遵循____原则。",
        "先进先出|FIFO；后进先出|LIFO",
    )
    assert packed["count"] == 2
    assert len(packed["stored_answer"]) <= 64
    graded = grade_submission(
        "队列遵循____原则，栈遵循____原则。",
        packed["options"],
        packed["stored_answer"],
        '["fifo", "后进 先出"]',
    )
    assert graded["correct"] is True
    assert [item["correct"] for item in graded["results"]] == [True, True]


def test_grade_rejects_swapped_blanks_and_blank_input():
    packed = pack_blank("____和____", "队列；栈")
    swapped = grade_submission("____和____", packed["options"], packed["stored_answer"], '["栈","队列"]')
    assert swapped["correct"] is False
    assert swapped["results"][0]["correct"] is False
    empty = grade_submission("____和____", packed["options"], packed["stored_answer"], '["队列",""]')
    assert empty["correct"] is False


def test_student_view_hides_answers():
    packed = pack_blank("循环队列牺牲一个____", "存储单元|空间")
    view = student_view("blank", "循环队列牺牲一个____", packed["options"], packed["stored_answer"])
    assert view["options"] == []
    assert view["blanks"] == [{"index": 1}]
    assert "存储单元" not in str(view["blanks"])
    choice = student_view("single", "题干", [{"key": "A", "text": "栈"}], "A")
    assert choice["options"][0]["key"] == "A"
    assert choice["blanks"] == []


def test_preview_accepts_blank_and_keeps_single_choice():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    blank = preview_questions(db, "C_TEST", questions=[{
        "stem": "队列遵循____原则。",
        "type": "填空题",
        "answer": "先进先出|FIFO",
        "difficulty": 2,
        "score": 5,
    }])
    assert blank["ready"] is True
    assert blank["questions"][0]["type"] == "blank"
    assert blank["questions"][0]["options"][0]["accept"] == ["先进先出", "FIFO"]

    choice = preview_questions(db, "C_TEST", questions=[{
        "stem": "哪种结构先进先出？",
        "type": "单选题",
        "options": [{"key": "A", "text": "栈"}, {"key": "B", "text": "队列"}],
        "answer": "b",
    }])
    assert choice["ready"] is True
    assert choice["questions"][0]["type"] == "single"
    assert choice["questions"][0]["answer"] == "B"


def test_preview_text_without_options_becomes_blank():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    result = preview_questions(db, "C_TEST", text="1. 栈遵循____原则。\n答案：后进先出\n解析：后进先出。")
    assert result["ready"] is True
    assert result["questions"][0]["type"] == "blank"
    assert result["questions"][0]["options"][0]["accept"] == ["后进先出"]
