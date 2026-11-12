from flask import Flask

from app.people.api import people_api
from app.people.events import LeadConverted, RecordsMerged


def init_people(app: Flask) -> None:
    app.register_api(people_api)


__all__ = ["LeadConverted", "RecordsMerged", "init_people"]
