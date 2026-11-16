"""Веб-семейство дневника: профиль семьи, календарь событий, карточка человека."""

from datetime import date

from diarysdk._api.base import Api
from diarysdk._wire.common import parse
from diarysdk._wire.web import EventsResponse, PersonData, WebFamilyProfile


class WebAPI(Api):
    async def get_family_web_profile(self) -> WebFamilyProfile:
        response = await self._get(
            self._hosts.dnevnik,
            "/api/family/web/v1/profile",
            call="profile",
            headers={"x-mes-subsystem": "familyweb"},
            params={"nocache": True},
        )
        return parse(WebFamilyProfile, response)

    async def get_person_data(self, person_id: str) -> PersonData:
        response = await self._get(
            self._hosts.dnevnik,
            f"/api/persondata/v1/persons/{person_id}",
            call="persondata",
            headers={"x-mes-subsystem": "headerweb"},
        )
        return parse(PersonData, response)

    async def get_events(
        self, person_id: str, mes_role: str, begin_date: date, end_date: date, expand: str
    ) -> EventsResponse:
        response = await self._get(
            self._hosts.dnevnik,
            "/api/eventcalendar/v1/api/events",
            call="schedule.events",
            headers={"x-mes-subsystem": "familyweb", "x-mes-role": mes_role},
            params={
                "person_ids": person_id,
                "begin_date": begin_date,
                "end_date": end_date,
                "expand": expand,
            },
        )
        return parse(EventsResponse, response)
