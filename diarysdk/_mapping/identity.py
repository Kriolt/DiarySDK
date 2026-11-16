"""/v1/identity из family/web/v1/profile и карточки человека.

Профиль даёт ФИО, контакты, личное дело, группы, группу здоровья для
физкультуры и представителей; часть этих полей модель ответа не
объявляет — они читаются через field(). СНИЛС ученика — из профиля, а если
там пусто, из карточки. Карточка даёт место рождения, документы, адреса,
историю обучения и контакты; служебные метаданные её записей (кто и когда
правил, статусы сверки, сроки действия) не берутся.
"""

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from diarysdk._mapping.common import (
    as_date,
    as_datetime,
    as_int,
    as_json,
    as_text,
    class_unit,
    field,
    school_brief,
)
from diarysdk._mapping.context import the_child
from diarysdk._wire.web import PersonData, WebFamilyProfile
from diarysdk.errors import NotFound, UnsupportedContact
from diarysdk.models.identity import (
    Address,
    Contact,
    Document,
    DocumentAct,
    DocumentAttachment,
    Education,
    EducationClass,
    GradeBook,
    Health,
    Identity,
    IdentityPerson,
    Representative,
    Specialty,
    StudyGroup,
    is_email_address,
)


def _name(value: Any) -> str | None:
    """Название из вложенного справочника дневника ({id, name, …})."""
    return as_text(field(value, "name"))


def _section[T](build: Callable[[PersonData], list[T]], card: PersonData | None) -> list[T]:
    """Раздел карточки. Нет карточки или наша схема не приняла раздел, который
    модель ответа разобрала, — пустой список, а не 500 на всю карточку: как и
    при карточке, которая не далась вовсе."""
    if card is None:
        return []
    try:
        return build(card)
    except ValidationError:
        return []


def _documents(card: PersonData) -> list[Document]:
    result = []
    for doc in card.documents or []:
        data = field(doc, "data")
        result.append(
            Document(
                type_id=doc.document_type_id,
                type=_name(doc.document_type),
                series=doc.series,
                number=doc.number,
                issuer=doc.issuer,
                issued=as_date(doc.issued),
                expiration=as_date(doc.expiration),
                subdivision_code=doc.subdivision_code,
                act=DocumentAct(
                    number=as_text(field(data, "act_number")),
                    date=as_date(field(data, "act_date")),
                ),
                comment=as_text(field(doc, "comment")),
                attachments=[
                    DocumentAttachment(
                        id=as_text(field(item, "id")),
                        name=as_text(field(item, "name")),
                        uploaded_at=as_datetime(field(item, "uploaded_at")),
                    )
                    for item in doc.attachments or []
                ],
            )
        )
    return result


def _addresses(card: PersonData) -> list[Address]:
    return [
        Address(
            type_id=item.address_type_id,
            type=_name(item.address_type),
            address=as_text(field(item.address, "address")),
            flat=as_text(field(item.address, "flat")),
        )
        for item in card.addresses or []
    ]


def _education(card: PersonData) -> list[Education]:
    result = []
    for item in card.education or []:
        klass = item.class_
        result.append(
            Education(
                organization_id=item.organization_id,
                class_=EducationClass(
                    id=as_int(field(klass, "id")),
                    uid=as_text(field(klass, "uid")),
                    name=as_text(field(klass, "name")),
                    letter=as_text(field(klass, "letter")),
                    parallel=_name(field(klass, "parallel")),
                    academic_year_id=as_int(field(klass, "academic_year_id")),
                ),
                form=_name(item.education_form),
                financing=_name(item.financing_type),
                service_type=_name(item.service_type),
                # Справочник, как у соседей; в наблюдениях всегда null, поэтому
                # строку без справочника тоже принимаем.
                deduction_reason=(
                    _name(item.deduction_reason)
                    if isinstance(item.deduction_reason, dict)
                    else as_text(item.deduction_reason)
                ),
                began=as_date(item.training_begin_at),
                ended=as_date(item.training_end_at),
                notes=item.notes,
            )
        )
    return result


def _contacts(card: PersonData) -> list[Contact]:
    """contacts в модели ответа не типизирован; форма — по наблюдениям
    Элементы не-словари пропускаются."""
    contacts = card.contacts if isinstance(card.contacts, list) else []
    return [
        Contact(
            id=as_int(item.get("id")),
            type_id=as_int(item.get("type_id")),
            type=_name(item.get("type")),
            value=as_text(item.get("data")),
            is_default=item.get("default"),
        )
        for item in contacts
        if isinstance(item, dict)
    ]


_PHONE_WORDS = ("телефон", "phone", "моб")


def email_contact(card: PersonData, contact_id: int) -> dict[str, Any]:
    """Контакт карточки с этим id, как он пришёл (со всеми полями). Нет такого
    у самого ученика — NotFound; не адрес почты — UnsupportedContact."""
    contacts = card.contacts if isinstance(card.contacts, list) else []
    found = next(
        (
            item
            for item in contacts
            if isinstance(item, dict)
            and isinstance(item.get("id"), int)
            and not isinstance(item.get("id"), bool)
            and item["id"] == contact_id
        ),
        None,
    )
    if found is None:
        raise NotFound()
    data = found.get("data")
    type_name = (_name(found.get("type")) or "").lower()
    if not is_email_address(data) or any(w in type_name for w in _PHONE_WORDS):
        raise UnsupportedContact()
    return found


def identity(profile: WebFamilyProfile, card: PersonData | None) -> Identity:
    child = the_child(profile)
    return Identity(
        person=IdentityPerson(
            last_name=child.last_name,
            first_name=child.first_name,
            middle_name=child.middle_name,
            birth_date=as_date(child.birth_date),
            sex=child.sex,
            phone=child.phone or None,
            email=child.email or None,
            snils=child.snils or (card.snils if card else None) or None,
            grade_book=GradeBook(
                number=as_text(field(child, "grade_book_number")),
                date=as_date(field(child, "grade_book_date")),
            ),
            health=Health(pe_group_id=as_int(field(child, "physical_training_health_group_id"))),
            education_level_id=as_int(field(child, "education_level_id")),
            service_type_id=as_int(field(child, "service_type_id")),
            parallel_curriculum_id=child.parallel_curriculum_id,
            specialty=Specialty(
                code=as_text(field(child, "profession_specialty_code")),
                name=as_text(field(child, "profession_specialty_name")),
            ),
            user_id=child.user_id,
            sudir_login=child.sudir_login,
            sudir_account_exists=child.sudir_account_exists,
            is_legal_representative=child.is_legal_representative,
            groups=[
                StudyGroup(
                    id=group.id, name=group.name, subject_id=group.subject_id, is_fake=group.is_fake
                )
                for group in child.groups or []
            ],
            birthplace=card.birthplace if card else None,
            citizenship_id=card.citizenship_id if card else None,
            documents=_section(_documents, card),
            addresses=_section(_addresses, card),
            education=_section(_education, card),
            contacts=_section(_contacts, card),
            categories=as_json(card.categories) if card else None,
            agents=as_json(card.agents) if card else None,
            preventions=as_json(card.preventions) if card else None,
            citizenship=as_json(card.citizenship) if card else None,
            children=as_json(card.children) if card else None,
        ),
        school=school_brief(child),
        class_=class_unit(child),
        representatives=[
            Representative(
                type=rep.type,
                type_id=as_int(field(rep, "type_id")),
                guid=as_text(field(rep, "person_id")),
                last_name=rep.last_name,
                first_name=rep.first_name,
                middle_name=rep.middle_name,
                sex=rep.sex,
                birth_date=as_date(rep.birth_date),
                phone=rep.phone or None,
                email=rep.email or None,
                snils=rep.snils or None,
            )
            for rep in child.representatives or []
        ],
    )
