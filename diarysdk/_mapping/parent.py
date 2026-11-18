"""Родитель из family/web/v1/profile: контекст, профиль, список детей."""

from datetime import datetime

from diarysdk._mapping.common import school_brief
from diarysdk._port import ParentContext
from diarysdk._wire.web import WebFamilyProfile
from diarysdk.errors import NotForRole, UpstreamFormat
from diarysdk.models.me import TokenExpiry
from diarysdk.models.parent import Child, ParentMe


def parent_context(
    profile: WebFamilyProfile, expires_at: datetime, token_guid: str | None
) -> ParentContext:
    """Контекст владельца-родителя. Токен не родителя — NotForRole(role="student").

    GUID карточки — claim `msh` токена (живьём: у родителя это его person_id);
    нет claim — представитель ребёнка с тем же СНИЛС, что у профиля.
    """
    owner = profile.profile
    if owner is None or owner.type != "parent":
        raise NotForRole("Токен не родителя: используйте diary.student(token)", role="student")
    if owner.id is None:
        raise UpstreamFormat(problems=["profile.id: нет в профиле"])
    return ParentContext(
        profile_id=owner.id,
        person_guid=token_guid or _guid_by_snils(profile),
        expires_at=expires_at,
        profile=profile,
    )


def _guid_by_snils(profile: WebFamilyProfile) -> str | None:
    snils = profile.profile.snils if profile.profile else None
    if not snils:
        return None
    for child in profile.children or []:
        for rep in child.representatives or []:
            if rep.snils == snils and rep.person_id:
                return rep.person_id
    return None


def me(profile: WebFamilyProfile, expires_at: datetime) -> ParentMe:
    owner = profile.profile
    return ParentMe(
        first_name=owner.first_name if owner else None,
        last_name=owner.last_name if owner else None,
        middle_name=owner.middle_name if owner else None,
        type=owner.type if owner else None,
        email=(owner.email or None) if owner else None,
        phone=(owner.phone or None) if owner else None,
        token=TokenExpiry(expires_at=expires_at),
    )


def children(profile: WebFamilyProfile) -> list[Child]:
    return [
        Child(
            id=child.id,
            first_name=child.first_name,
            last_name=child.last_name,
            middle_name=child.middle_name,
            school=school_brief(child),
            class_name=child.class_name,
            is_legal_representative=child.is_legal_representative,
        )
        for child in profile.children or []
        if child.id is not None
    ]
