"""/v1/school из family/mobile/v1/school_info."""

from diarysdk._mapping.common import as_int, field
from diarysdk._wire.mobile import SchoolInfo
from diarysdk.models.common import PersonName
from diarysdk.models.school import Branch, School, Teacher


def school(info: SchoolInfo) -> School:
    return School(
        name=info.name,
        type=info.type,
        principal=info.principal,
        address=info.address.address if info.address else None,
        phone=info.phone,
        email=info.email,
        website=info.website_link,
        classroom_teachers=[
            PersonName(last_name=t.last_name, first_name=t.first_name, middle_name=t.middle_name)
            for t in info.classroom_teachers or []
        ],
        teachers=[
            Teacher(
                last_name=t.last_name,
                first_name=t.first_name,
                middle_name=t.middle_name,
                subjects=t.subject_names or [],
            )
            for t in info.teachers or []
        ],
        branches=[
            Branch(
                name=b.name,
                address=b.address,
                is_main=b.is_main_building,
                # building_id модель ответа не объявляет.
                building_id=as_int(field(b, "building_id")),
                is_student_building=b.is_student_building,
                type=b.type,
            )
            for b in info.branches or []
        ],
        id=info.id,
        county=info.address.county if info.address else None,
        district=info.address.district if info.address else None,
    )
