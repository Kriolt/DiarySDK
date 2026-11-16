"""/v1/identity — полная карточка ученика и данные его законных представителей.

Назначение — отвечать на запросы администрации о нарушителях. СНИЛС и данные
представителей отдаются по решению владельца проекта, всё остальное из
профиля и карточки человека — по принятому решению (см. спек).
"""

import datetime as dt
import re
from typing import Self

from pydantic import ConfigDict, Field, JsonValue, model_validator

from diarysdk.models.common import ClassUnit, PersonName, Schema, SchoolBrief


class IdentityBase(PersonName):
    """Общее у ученика и представителя."""

    birth_date: dt.date | None = None
    sex: str | None = None
    phone: str | None = None
    email: str | None = None
    snils: str | None = None


class GradeBook(Schema):
    """Личное дело."""

    number: str | None = None
    date: dt.date | None = None


class Health(Schema):
    # physical_training_health_group_id — группа здоровья для физкультуры,
    # код дневника как есть.
    pe_group_id: int | None = None


class Specialty(Schema):
    code: str | None = None
    name: str | None = None


class StudyGroup(Schema):
    id: int | None = None
    name: str | None = None
    subject_id: int | None = None
    is_fake: bool | None = None


class DocumentAct(Schema):
    """Актовая запись (data.act_number и data.act_date дневника)."""

    number: str | None = None
    date: dt.date | None = None


class DocumentAttachment(Schema):
    # Строка (скорее всего UUID).
    id: str | None = None
    name: str | None = None
    uploaded_at: dt.datetime | None = None


class Document(Schema):
    type_id: int | None = None
    # Название типа из ответа дневника («Свидетельство о рождении»).
    type: str | None = None
    series: str | None = None
    number: str | None = None
    issuer: str | None = None
    issued: dt.date | None = None
    expiration: dt.date | None = None
    subdivision_code: str | None = None
    act: DocumentAct = Field(default_factory=DocumentAct)
    comment: str | None = None
    attachments: list[DocumentAttachment] = Field(default_factory=list)


class Address(Schema):
    type_id: int | None = None
    type: str | None = None
    address: str | None = None
    flat: str | None = None


class EducationClass(Schema):
    id: int | None = None
    uid: str | None = None
    name: str | None = None
    letter: str | None = None
    # Название параллели («10»).
    parallel: str | None = None
    academic_year_id: int | None = None


class Education(Schema):
    """Запись истории обучения; у формы, финансирования, вида услуги и
    причины выбытия — названия из ответа дневника."""

    organization_id: int | None = None
    class_: EducationClass = Field(default_factory=EducationClass, alias="class")
    form: str | None = None
    financing: str | None = None
    service_type: str | None = None
    deduction_reason: str | None = None
    began: dt.date | None = None
    ended: dt.date | None = None
    notes: str | None = None


class Contact(Schema):
    # id — для PUT /v1/identity/contacts/{contact_id}.
    id: int | None = None
    type_id: int | None = None
    type: str | None = None
    value: str | None = None
    is_default: bool | None = None


# Без пробелов и управляющих символов (в том числе переводов строки).
_NO_SPACE_OR_CONTROL = re.compile(r"[^\s\x00-\x1f\x7f]+")


def is_email_address(value: object) -> bool:
    """Адрес почты по правилу сервиса: ровно одна @, обе части непустые, без
    пробелов и управляющих символов. Одно правило и для нового значения
    (ContactUpdate), и для текущего контакта (сервис)."""
    if not isinstance(value, str) or not _NO_SPACE_OR_CONTROL.fullmatch(value):
        return False
    local, at, domain = value.partition("@")
    return bool(at and local and domain and "@" not in domain)


class ContactUpdate(Schema):
    """Новый адрес почты в контакте ученика. Больше ничего менять нельзя:
    лишние поля (в том числе is_default) — ошибка."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=3, max_length=255)

    @model_validator(mode="after")
    def _email(self) -> Self:
        if not is_email_address(self.value):
            raise ValueError("нужен адрес почты: ровно одна @ с непустыми частями, без пробелов")
        return self


class IdentityPerson(IdentityBase):
    grade_book: GradeBook = Field(default_factory=GradeBook)
    health: Health = Field(default_factory=Health)
    education_level_id: int | None = None
    service_type_id: int | None = None
    parallel_curriculum_id: int | None = None
    specialty: Specialty = Field(default_factory=Specialty)
    user_id: int | None = None
    sudir_login: str | None = None
    sudir_account_exists: bool | None = None
    is_legal_representative: bool | None = None
    groups: list[StudyGroup] = Field(default_factory=list)
    # Из карточки человека; не далась — null и пустые списки.
    birthplace: str | None = None
    citizenship_id: int | None = None
    documents: list[Document] = Field(default_factory=list)
    addresses: list[Address] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    # Как пришли: в наблюдениях у двух учеников всегда null, форма не
    # подтверждена.
    categories: JsonValue = None
    agents: JsonValue = None
    preventions: JsonValue = None
    citizenship: JsonValue = None
    children: JsonValue = None


class Representative(IdentityBase):
    # Тип представителя как в дневнике (мать, отец, опекун) и его код.
    type: str | None = None
    type_id: int | None = None
    guid: str | None = None


class Identity(Schema):
    person: IdentityPerson
    school: SchoolBrief
    class_: ClassUnit = Field(alias="class")
    representatives: list[Representative] = Field(default_factory=list)
