from pydantic import Field

from diarysdk.models.common import PersonName, Schema


class Teacher(PersonName):
    subjects: list[str] = Field(default_factory=list)


class Branch(Schema):
    name: str | None = None
    address: str | None = None
    is_main: bool | None = None
    building_id: int | None = None
    is_student_building: bool | None = None
    type: str | None = None


class School(Schema):
    name: str | None = None
    type: str | None = None
    principal: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    classroom_teachers: list[PersonName] = Field(default_factory=list)
    teachers: list[Teacher] = Field(default_factory=list)
    branches: list[Branch] = Field(default_factory=list)
    id: int | None = None
    # Округ и район из адреса школы.
    county: str | None = None
    district: str | None = None
