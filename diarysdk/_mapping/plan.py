"""Учебный план → публичные модели."""

from typing import Any

from pydantic import TypeAdapter, ValidationError

from diarysdk._mapping.common import as_date, as_text
from diarysdk._wire.plan import WireProgramModule, WireTestLessons, WireThematicFrame
from diarysdk.errors import UpstreamFormat
from diarysdk.models.common import Subject
from diarysdk.models.curriculum import (
    ControlWork,
    ProgramLesson,
    ProgramModule,
    ProgramTopic,
    SubjectTopic,
    TopicResult,
)

_MODULES = TypeAdapter(list[WireProgramModule])
_FRAMES = TypeAdapter(list[WireThematicFrame])
_TESTS = TypeAdapter(WireTestLessons)


def _parse[T](adapter: TypeAdapter[T], data: Any) -> T:
    try:
        return adapter.validate_python(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None


def work_program(data: Any) -> list[ProgramModule]:
    return [
        ProgramModule(
            title=module.title,
            ordinal=module.ordinal,
            subject_id=module.subject_id,
            topics=[
                ProgramTopic(
                    title=topic.title,
                    ordinal=topic.ordinal,
                    lessons=[
                        ProgramLesson(
                            title=lesson.title,
                            ordinal=lesson.ordinal,
                            date=as_date(lesson.date),
                            lesson_id=lesson.lesson_schedule_id,
                            oge_tasks=list(lesson.oge_task_name or []),
                            ege_tasks=list(lesson.ege_task_name or []),
                        )
                        for lesson in topic.lessons or []
                    ],
                )
                for topic in module.topics or []
            ],
        )
        for module in _parse(_MODULES, data)
    ]


def subject_topics(data: Any) -> list[SubjectTopic]:
    return [
        SubjectTopic(
            id=frame.id,
            title=frame.title,
            results=[
                TopicResult(
                    id=r.id,
                    text=r.text_for_family or r.description,
                    type=r.type_result,
                    mandatory=r.mandatory,
                )
                for r in frame.results or []
            ],
        )
        for frame in _parse(_FRAMES, data)
    ]


def control_works(data: Any) -> list[ControlWork]:
    return [
        ControlWork(
            date=as_date(item.test_lessons_date),
            subject=Subject(id=item.subject_id, name=item.subject_name),
            form=item.control_form_name,
            theme=item.lesson_theme,
            lesson_id=item.lesson_id,
            mark=as_text(item.test_lessons_grade),
            is_absent=item.is_absent,
            is_success=item.is_success,
        )
        for item in _parse(_TESTS, data).items or []
    ]
