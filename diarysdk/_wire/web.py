"""Ответы веб-семейства: профиль семьи (family/web), календарь событий и
карточка человека (persondata)."""

from typing import Any

from pydantic import Field

from diarysdk._wire.common import DT, Wire
from diarysdk._wire.mobile import Mark


class Profile(Wire):
    id: int | None = None


class School(Wire):
    id: int | None = None
    name: str | None = None
    short_name: str | None = None
    county: str | None = None


class Group(Wire):
    id: int | None = None
    name: str | None = None
    subject_id: int | None = None
    is_fake: bool | None = None


class Person(Wire):
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    birth_date: DT | None = None
    sex: str | None = None
    phone: str | None = None
    email: str | None = None
    snils: str | None = None
    type: str | None = None


class Representative(Person):
    pass


class Child(Person):
    user_id: int | None = None
    id: int | None = None
    school: School | None = None
    class_name: str | None = None
    class_level_id: int | None = None
    class_unit_id: int | None = None
    groups: list[Group] | None = None
    representatives: list[Representative] | None = None
    sections: list | None = None
    sudir_account_exists: bool | None = None
    sudir_login: str | None = None
    is_legal_representative: bool | None = None
    parallel_curriculum_id: int | None = None
    contingent_guid: str | None = None
    enrollment_date: DT | None = None


class WebFamilyProfile(Wire):
    profile: Profile | None = None
    children: list[Child] | None = None


class HomeworkEntry(Wire):
    description: str | None = None
    attachments: list | None = None


class Homework(Wire):
    presence_status_id: int | None = None
    total_count: int | None = None
    execute_count: int | None = None
    descriptions: list[str] | None = None
    entries: list[HomeworkEntry] | None = None


class Event(Wire):
    id: int | None = None
    start_at: DT | None = None
    finish_at: DT | None = None
    source: str | None = None
    source_id: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    room_name: str | None = None
    room_number: str | None = None
    replaced: bool | None = None
    replaced_teacher_id: int | None = None
    lesson_type: str | None = None
    course_lesson_type: str | None = None
    link_to_join: str | None = None
    cancelled: bool | None = None
    is_missed_lesson: bool | None = None
    absence_reason_id: int | None = None
    nonattendance_reason_id: int | None = None
    health_status: str | None = None
    homework: Homework | None = None
    marks: list[Mark] | None = None


class EventsResponse(Wire):
    response: list[Event] | None = None


class Reference(Wire):
    """Справочник дневника: {id, name, …}."""

    id: int | None = None
    name: str | None = None


class Attachment(Wire):
    id: str | None = None
    name: str | None = None
    uploaded_at: str | None = None


class Document(Wire):
    document_type_id: int | None = None
    document_type: Reference | None = None
    series: str | None = None
    number: str | None = None
    subdivision_code: str | None = None
    issuer: str | None = None
    issued: str | None = None
    expiration: Any = None
    attachments: list[Attachment] | None = None


class AddressText(Wire):
    address: str | None = None
    flat: str | None = None


class Address(Wire):
    address_type_id: int | None = None
    address_type: Reference | None = None
    address: AddressText | None = None


class SchoolClass(Wire):
    id: int | None = None
    uid: str | None = None
    name: str | None = None
    letter: str | None = None
    academic_year_id: int | None = None
    parallel: Reference | None = None


class Education(Wire):
    organization_id: int | None = None
    notes: Any = None
    service_type: Reference | None = None
    training_begin_at: str | None = None
    training_end_at: str | None = None
    class_: SchoolClass | None = Field(None, alias="class")
    education_form: Reference | None = None
    financing_type: Reference | None = None
    deduction_reason: Any = None


class PersonData(Wire):
    birthplace: str | None = None
    snils: str | None = None
    citizenship_id: int | None = None
    addresses: list[Address] | None = None
    documents: list[Document] | None = None
    contacts: Any = None
    preventions: Any = None
    categories: Any = None
    agents: Any = None
    children: Any = None
    education: list[Education] | None = None
    citizenship: Any = None
