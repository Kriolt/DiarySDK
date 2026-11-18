"""Ответы учебного плана (ej/plan/family, family/web programs): читаемые поля."""

from typing import Any

from diarysdk._wire.common import DT, Wire


class WireProgramLesson(Wire):
    title: str | None = None
    lesson_schedule_id: int | None = None
    ordinal: int | None = None
    date: DT | None = None
    oge_task_name: list[str] | None = None
    ege_task_name: list[str] | None = None


class WireProgramTopic(Wire):
    title: str | None = None
    ordinal: int | None = None
    lessons: list[WireProgramLesson] | None = None


class WireProgramModule(Wire):
    title: str | None = None
    ordinal: int | None = None
    subject_id: int | None = None
    topics: list[WireProgramTopic] | None = None


class WireTopicResult(Wire):
    id: int | None = None
    text_for_family: str | None = None
    description: str | None = None
    type_result: str | None = None
    mandatory: str | None = None


class WireThematicFrame(Wire):
    id: int | None = None
    title: str | None = None
    results: list[WireTopicResult] | None = None


class WireTestLesson(Wire):
    test_lessons_date: DT | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    control_form_name: str | None = None
    lesson_theme: str | None = None
    lesson_id: int | None = None
    test_lessons_grade: Any = None
    is_absent: bool | None = None
    is_success: bool | None = None


class WireTestLessons(Wire):
    items: list[WireTestLesson] | None = None
