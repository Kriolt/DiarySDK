"""Мобильное семейство дневника (family/mobile/v1/*) и рейтинг."""

from datetime import date

from diarysdk._api.rating import RatingAPI
from diarysdk._wire.common import parse, parse_list
from diarysdk._wire.mobile import (
    Marks,
    Notification,
    ParallelCurriculum,
    PeriodsSchedules,
    SchoolInfo,
    SubjectMarksForSubject,
    SubjectsMarks,
)


class MobileAPI(RatingAPI):
    async def _school_api(self, path: str, call: str, profile_id: int, params: dict):
        return await self._get(
            self._hosts.school_api,
            path,
            call=call,
            headers=self._mobile_headers(profile_id),
            params=params,
        )

    async def get_marks(
        self, student_id: int, profile_id: int, from_date: date, to_date: date
    ) -> Marks:
        response = await self._school_api(
            "/family/mobile/v1/marks",
            "marks",
            profile_id,
            {"student_id": student_id, "from": from_date, "to": to_date},
        )
        return parse(Marks, response)

    async def get_subjects_marks(self, profile_id: int, student_id: int) -> SubjectsMarks:
        response = await self._school_api(
            "/family/mobile/v1/subject_marks",
            "subjects.marks",
            profile_id,
            {"student_id": student_id},
        )
        return parse(SubjectsMarks, response)

    async def get_subject_marks_for_subject(
        self, student_id: int, profile_id: int, subject_name: str
    ) -> SubjectMarksForSubject:
        response = await self._school_api(
            "/family/mobile/v1/subject_marks/for_subject",
            "subject_marks.for_subject",
            profile_id,
            {"student_id": student_id, "subject_name": subject_name},
        )
        return parse(SubjectMarksForSubject, response)

    async def get_school_info(
        self, profile_id: int, school_id: int, class_unit_id: int
    ) -> SchoolInfo:
        response = await self._school_api(
            "/family/mobile/v1/school_info",
            "school.info",
            profile_id,
            {"school_id": school_id, "class_unit_id": class_unit_id},
        )
        return parse(SchoolInfo, response)

    async def get_notifications(self, student_id: int, profile_id: int) -> list[Notification]:
        response = await self._school_api(
            "/family/mobile/v1/notifications/search",
            "notifications",
            profile_id,
            {"student_id": student_id},
        )
        return parse_list(Notification, response)

    async def get_periods_schedules(
        self, student_id: int, profile_id: int, from_date: date, to_date: date
    ) -> list[PeriodsSchedules]:
        response = await self._school_api(
            "/family/mobile/v1/periods_schedules",
            "periods_schedules",
            profile_id,
            {"student_id": student_id, "from": from_date, "to": to_date},
        )
        return parse_list(PeriodsSchedules, response)

    async def get_programs_parallel_curriculum(
        self, curriculum_id: int, profile_id: int, student_id: int
    ) -> ParallelCurriculum:
        response = await self._school_api(
            f"/family/mobile/v1/programs/parallel_curriculum/{curriculum_id}",
            "curriculum",
            profile_id,
            {"student_id": student_id},
        )
        return parse(ParallelCurriculum, response)
