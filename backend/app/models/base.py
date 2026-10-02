"""Base classes for MongoDB documents."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.database import utcnow


class Embedded(BaseModel):
    """A sub-document stored inside its parent."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class GeoPoint(Embedded):
    """GeoJSON point. Note the order: [longitude, latitude]. Indexed with 2dsphere."""

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]

    @classmethod
    def of(cls, lat: float, lng: float) -> GeoPoint:
        return cls(coordinates=(float(lng), float(lat)))

    @property
    def lat(self) -> float:
        return self.coordinates[1]

    @property
    def lng(self) -> float:
        return self.coordinates[0]


class Document(BaseModel):
    """A top-level document. `id` is stored as `_id`.

    Fields declared with `exclude=True` are references resolved at read time (see
    app/services/loaders.py); they are never written to the database.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: int = Field(default=0, alias="_id")

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    @classmethod
    def encode_fields(cls, fields: dict[str, Any]) -> dict[str, Any]:
        """Turn attribute values into BSON-ready values for a partial `$set`."""
        return {k: (v.model_dump(by_alias=True) if isinstance(v, BaseModel) else
                    [i.model_dump(by_alias=True) if isinstance(i, BaseModel) else i for i in v]
                    if isinstance(v, list) else v)
                for k, v in fields.items()}


class Timestamps(BaseModel):
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
