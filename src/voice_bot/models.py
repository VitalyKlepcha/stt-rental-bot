"""Pydantic data models for the rental request domain.

These models serve as the JSON schema for OpenAI structured output (GPT-4o-mini).
The OpenAI SDK uses ``model_json_schema()`` to generate the schema that constrains
the LLM's response, so field ``description`` values are written in Russian to guide
the model during entity extraction.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EquipmentItem(BaseModel):
    """A single piece of rental equipment with an optional quantity."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="Наименование оборудования (например, «Экскаватор JCB 3CX»)",
    )
    quantity: int = Field(
        default=1,
        ge=1,
        description="Количество единиц оборудования (минимум 1)",
    )


class RentalRequestData(BaseModel):
    """Structured rental request extracted from a transcribed voice message.

    All optional fields default to ``None`` (or empty list for equipment) so the
    LLM can return ``null`` for information not mentioned in the audio.
    """

    model_config = ConfigDict(extra="forbid")

    client_name: str | None = Field(
        default=None,
        description="Имя или наименование клиента",
    )
    contact_phone: str | None = Field(
        default=None,
        description="Контактный телефон клиента в международном формате, если возможно",
    )
    equipment: list[EquipmentItem] = Field(
        default_factory=list,
        description="Список арендуемого оборудования с количеством единиц",
    )
    rental_start_date: str | None = Field(
        default=None,
        description="Дата начала аренды в формате ISO (ГГГГ-ММ-ДД), если удалось определить",
    )
    rental_end_date: str | None = Field(
        default=None,
        description="Дата окончания аренды в формате ISO (ГГГГ-ММ-ДД), если удалось определить",
    )
    rental_duration_days: int | None = Field(
        default=None,
        ge=1,
        description="Длительность аренды в днях",
    )
    delivery_address: str | None = Field(
        default=None,
        description="Адрес доставки оборудования",
    )
    preferred_delivery_time: str | None = Field(
        default=None,
        description="Предпочтительное время доставки",
    )
    special_requirements: str | None = Field(
        default=None,
        description="Особые требования, пожелания или примечания клиента",
    )
    urgency: Literal["normal", "urgent"] = Field(
        default="normal",
        description="Срочность заявки: «urgent» — только если клиент явно сказал, что срочно",
    )

    def is_empty(self) -> bool:
        """Return ``True`` when every field is at its default (no data extracted)."""
        return (
            self.client_name is None
            and self.contact_phone is None
            and len(self.equipment) == 0
            and self.rental_start_date is None
            and self.rental_end_date is None
            and self.rental_duration_days is None
            and self.delivery_address is None
            and self.preferred_delivery_time is None
            and self.special_requirements is None
            and self.urgency == "normal"
        )
