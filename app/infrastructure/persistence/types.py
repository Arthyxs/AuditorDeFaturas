"""Shared PostgreSQL persistence types and enum conventions."""

from enum import StrEnum

from sqlalchemy import Enum as SqlEnum

MONEY_PRECISION = 20
MONEY_SCALE = 6


class PersistedEnum(StrEnum):
    """Base for string-valued enums stored with database check constraints."""


def enum_values(enum_class: type[PersistedEnum]) -> list[str]:
    """Persist enum values rather than Python member names."""
    return [member.value for member in enum_class]


def string_enum_type(
    enum_class: type[PersistedEnum], *, name: str, create_constraint: bool = True
) -> SqlEnum:
    """Build a portable string enum with validation and an explicit constraint."""
    longest_value = max(len(member.value) for member in enum_class)
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=create_constraint,
        validate_strings=True,
        values_callable=enum_values,
        length=longest_value,
    )
