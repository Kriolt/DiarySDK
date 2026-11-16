"""/v1/me из family/web/v1/profile."""

import re
from collections.abc import Iterable
from datetime import date, datetime

from diarysdk._mapping.common import as_date, class_unit, school_brief
from diarysdk._mapping.context import the_child
from diarysdk._wire.web import WebFamilyProfile
from diarysdk.models.me import Me, MePerson, Section, TokenExpiry

# «ф.-м.», «х.-б.», «соц.-эк.» — так профиль обучения пишут в названиях групп.
_PROFILE = re.compile(r"(?<![а-яё])([а-яё]{1,5})\.\s?-\s?([а-яё]{1,5})\.", re.IGNORECASE)


def study_profile(group_names: Iterable[str]) -> str | None:
    """Единственная аббревиатура профиля во всех группах; иначе null."""
    found = {
        f"{first.lower()}.-{second.lower()}."
        for name in group_names
        for first, second in _PROFILE.findall(name)
    }
    return found.pop() if len(found) == 1 else None


def _age(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def me(profile: WebFamilyProfile, expires_at: datetime, today: date) -> Me:
    child = the_child(profile)
    sections = [
        Section(id=item.get("id"), name=item.get("name"))
        for item in child.sections or []
        if isinstance(item, dict)
    ]
    return Me(
        person=MePerson(
            last_name=child.last_name,
            first_name=child.first_name,
            middle_name=child.middle_name,
            sex=child.sex,
            age=_age(as_date(child.birth_date), today),
            guid=child.contingent_guid,
        ),
        school=school_brief(child),
        class_=class_unit(child),
        study_profile=study_profile(group.name for group in child.groups or [] if group.name),
        sections=sections,
        enrolled_on=as_date(child.enrollment_date),
        token=TokenExpiry(expires_at=expires_at),
    )
