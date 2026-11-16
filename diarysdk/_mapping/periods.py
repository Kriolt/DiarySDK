"""/v1/periods из family/mobile/v1/periods_schedules."""

from diarysdk._mapping.common import as_date, as_json
from diarysdk._wire.mobile import PeriodsSchedules
from diarysdk.models.periods import PeriodDay


def periods(data: list[PeriodsSchedules]) -> list[PeriodDay]:
    return [
        PeriodDay(
            date=as_date(item.date),
            type=item.type,
            title=item.title,
            description=item.description,
            events=as_json(item.events),
        )
        for item in data
    ]
