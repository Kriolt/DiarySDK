"""Справки об обучении (сайт: «Справки»)."""

import datetime as dt

from diarysdk.models.common import Schema


class Certificate(Schema):
    """Заявка на справку. Форма не подтверждена: живые списки были пустыми,
    поля — по тому, что читает сайт."""

    id: int | str | None = None
    status_id: int | None = None
    # Название статуса из справочника дневника («Сформирована», …).
    status: str | None = None
    purpose: str | None = None
    requested_on: dt.date | None = None
    issued_on: dt.date | None = None
    valid_until: dt.date | None = None
