"""Request bodies of the API. Fields stay optional so the routes keep their
own required-parameter messages; type errors are reported by the app-wide
validation handler."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class InstanceDataBody(BaseModel):
    instance: str | None = None
    data: dict[str, Any] | None = None


class CoupledSystemBody(BaseModel):
    coupled_system: str | None = None


class CreateInstanceBody(BaseModel):
    property: str | None = None
    parent: str | None = None
    data: dict[str, Any] | None = None


class CreateClassInstanceBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    class_name: str | None = Field(None, alias='class')
    label: str | None = None


class ReplaceValueBody(BaseModel):
    instance: str | None = None
    property: str | None = None
    old_value: Any = None
    new_value: Any = None


class DeleteValueBody(BaseModel):
    instance: str | None = None
    property: str | None = None
    value: Any = None
    cascade: StrictBool = True


class DeleteValuesBody(BaseModel):
    instance: str | None = None
    properties: list[str] | None = None


class DeleteInstanceBody(BaseModel):
    instance: str | None = None
    cascade: StrictBool = True


class ImportKratosBody(BaseModel):
    data: dict[str, Any] | None = None
    label: str | None = None


class CreateCoupledBody(BaseModel):
    label: str | None = None


class CopyInstanceBody(BaseModel):
    instance: str | None = None
    parent: str | None = None
    data: dict[str, Any] | None = None


class CopyInstanceRecursivelyBody(CopyInstanceBody):
    depth: int | None = None
    recursive: bool = False
