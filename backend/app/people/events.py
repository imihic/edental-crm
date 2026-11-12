from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.platform.events import DomainEvent


@dataclass(frozen=True)
class LeadConverted(DomainEvent):

    lead_id: UUID
    patient_id: UUID


@dataclass(frozen=True)
class RecordsMerged(DomainEvent):

    kept_patient_id: UUID
    retired_kind: Literal["patient", "lead"]
    retired_id: UUID
