"""Рейтинг класса (хост дневника, заголовки мобильного семейства)."""

from datetime import date

from diarysdk._api.base import Api
from diarysdk._wire.common import parse_list
from diarysdk._wire.rating import RatingRankClass, RatingRankShort, RatingRankSubject


class RatingAPI(Api):
    def _mobile_headers(self, profile_id: int) -> dict[str, object]:
        return {
            "x-mes-subsystem": "familymp",
            "client-type": "diary-mobile",
            "profile-id": profile_id,
        }

    async def get_rating_rank_class(
        self, profile_id: int, person_id: str, class_unit_id: int, on: date
    ) -> list[RatingRankClass]:
        response = await self._get(
            self._hosts.dnevnik,
            "/api/ej/rating/v1/rank/class",
            call="rating.class",
            headers=self._mobile_headers(profile_id),
            params={"person_id": person_id, "classUnitId": class_unit_id, "date": on},
        )
        return parse_list(RatingRankClass, response)

    async def get_rating_rank_short(
        self, profile_id: int, person_id: str, begin_date: date, end_date: date
    ) -> list[RatingRankShort]:
        response = await self._get(
            self._hosts.dnevnik,
            "/api/ej/rating/v1/rank/rankShort",
            call="rating.short",
            headers=self._mobile_headers(profile_id),
            params={"personId": person_id, "beginDate": begin_date, "endDate": end_date},
        )
        return parse_list(RatingRankShort, response)

    async def get_rating_rank_subjects(
        self, profile_id: int, person_id: str, on: date
    ) -> list[RatingRankSubject]:
        response = await self._get(
            self._hosts.dnevnik,
            "/api/ej/rating/v1/rank/subjects",
            call="rating.subjects",
            headers=self._mobile_headers(profile_id),
            params={"personId": person_id, "date": on},
        )
        return parse_list(RatingRankSubject, response)
