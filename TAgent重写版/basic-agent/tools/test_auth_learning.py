"""账号下的课程学情和试卷归属不串课、不串人。"""

from __future__ import annotations

from app.repository.learning_store import LearningStore


def test_course_summary_and_exam_ownership(tmp_path):
    store = LearningStore(tmp_path / "learning.sqlite3")
    try:
        store.touch_student("student-a", "小明")
        store.touch_student("student-b", "小红")
        store.record_chat(student_id="student-a", course_id="course-a", mode="qa", model="m",
                          question="A", answer="A")
        store.record_chat(student_id="student-a", course_id="course-b", mode="qa", model="m",
                          question="B", answer="B")
        store.record_chat(student_id="student-b", course_id="course-a", mode="qa", model="m",
                          question="C", answer="C")
        store.record_exam_generated(student_id="student-a", course_id="course-a", exam_id="exam-a",
                                    model="m", title="试卷", topic=None, total_points=100)

        assert store.exam_belongs_to("exam-a", "student-a", "course-a")
        assert not store.exam_belongs_to("exam-a", "student-b", "course-a")
        assert not store.exam_belongs_to("exam-a", "student-a", "course-b")
        result = store.course_summary("course-a", ["student-a", "student-b"])
        assert result["totals"] == {
            "students": 2, "chat_turns": 2, "essay_reviews": 0, "exams_reviewed": 0
        }
        assert [row["chat_turns"] for row in result["students"]] == [1, 1]
        assert store.course_summary("course-b", ["student-a"])["totals"]["chat_turns"] == 1
    finally:
        store.close()
