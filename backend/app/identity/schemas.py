from typing import Literal

from pydantic import BaseModel


class OrganizationOut(BaseModel):
    id: str
    name: str


class OrganizationsResponse(BaseModel):
    organizations: list[OrganizationOut]


class OkResponse(BaseModel):
    status: Literal["ok"]
