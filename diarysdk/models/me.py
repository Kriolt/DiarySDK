from datetime import date, datetime

from pydantic import Field

from diarysdk.models.common import ClassUnit, PersonName, Schema, SchoolBrief


class MePerson(PersonName):
    sex: str | None = None
    age: int | None = None
    # contingent_guid — тот же GUID, что у ученика в рейтинге одноклассников.
    guid: str | None = None


class Section(Schema):
    id: int | None = None
    name: str | None = None


class TokenExpiry(Schema):
    # Не TokenInfo: так называется ответ /v1/auth/token (models/auth.py), а
    # одинаковые имена в OpenAPI превращаются в длинные с путём модуля.
    expires_at: datetime


class Me(Schema):
    person: MePerson
    school: SchoolBrief
    class_: ClassUnit = Field(alias="class")
    # Профиль обучения из названий групп («ф.-м.»); не разобрался — null.
    study_profile: str | None = None
    sections: list[Section] = Field(default_factory=list)
    enrolled_on: date | None = None
    token: TokenExpiry
