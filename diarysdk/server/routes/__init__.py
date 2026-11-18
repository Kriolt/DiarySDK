"""Маршруты /v1: параметры → сервис → ответ."""

from diarysdk.server.routes import (
    certificates,
    curriculum,
    exams,
    homework,
    identity,
    lessons,
    marks,
    me,
    notifications,
    parent,
    periods,
    rating,
    schedule,
    school,
    settings,
    subjects,
)

ALL = [
    me.router,
    school.router,
    marks.router,
    subjects.router,
    rating.router,
    schedule.router,
    lessons.router,
    homework.router,
    exams.router,
    identity.router,
    notifications.router,
    periods.router,
    curriculum.router,
    settings.router,
    certificates.router,
    parent.router,
]
