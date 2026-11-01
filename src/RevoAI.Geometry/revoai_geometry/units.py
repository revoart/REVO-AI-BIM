"""Unit handling shared by the engine and the Revit bridge.

Rules that later phases depend on:

* The engine's canonical length unit is the **metre**.
* Revit's internal unit is the **foot**; the add-in converts at the boundary.
* A scan's declared unit is never silently changed. Callers must either read a
  reliable unit from the file metadata or ask the user.
"""

from __future__ import annotations

from enum import Enum

METERS_PER_FOOT = 0.3048
METERS_PER_INCH = 0.0254
METERS_PER_US_SURVEY_FOOT = 1200.0 / 3937.0


class UnitSystem(str, Enum):
    MILLIMETERS = "millimeters"
    CENTIMETERS = "centimeters"
    METERS = "meters"
    INCHES = "inches"
    FEET = "feet"
    US_SURVEY_FEET = "usSurveyFeet"


METERS_PER_UNIT: dict[UnitSystem, float] = {
    UnitSystem.MILLIMETERS: 0.001,
    UnitSystem.CENTIMETERS: 0.01,
    UnitSystem.METERS: 1.0,
    UnitSystem.INCHES: METERS_PER_INCH,
    UnitSystem.FEET: METERS_PER_FOOT,
    UnitSystem.US_SURVEY_FEET: METERS_PER_US_SURVEY_FOOT,
}

#: Revit's internal length unit.
REVIT_INTERNAL_UNIT = UnitSystem.FEET

_ALIASES: dict[str, UnitSystem] = {
    "mm": UnitSystem.MILLIMETERS,
    "millimeter": UnitSystem.MILLIMETERS,
    "millimeters": UnitSystem.MILLIMETERS,
    "millimetre": UnitSystem.MILLIMETERS,
    "millimetres": UnitSystem.MILLIMETERS,
    "cm": UnitSystem.CENTIMETERS,
    "centimeter": UnitSystem.CENTIMETERS,
    "centimeters": UnitSystem.CENTIMETERS,
    "centimetre": UnitSystem.CENTIMETERS,
    "centimetres": UnitSystem.CENTIMETERS,
    "m": UnitSystem.METERS,
    "meter": UnitSystem.METERS,
    "meters": UnitSystem.METERS,
    "metre": UnitSystem.METERS,
    "metres": UnitSystem.METERS,
    "in": UnitSystem.INCHES,
    "inch": UnitSystem.INCHES,
    "inches": UnitSystem.INCHES,
    "ft": UnitSystem.FEET,
    "foot": UnitSystem.FEET,
    "feet": UnitSystem.FEET,
    "us survey foot": UnitSystem.US_SURVEY_FEET,
    "us survey feet": UnitSystem.US_SURVEY_FEET,
    "ussurveyfeet": UnitSystem.US_SURVEY_FEET,
    "usft": UnitSystem.US_SURVEY_FEET,
    "ftus": UnitSystem.US_SURVEY_FEET,
}


def parse_unit(value: UnitSystem | str) -> UnitSystem:
    """Parse a unit name or common abbreviation.

    Raises ``ValueError`` rather than guessing, because a wrong unit silently
    corrupts every downstream dimension.
    """

    if isinstance(value, UnitSystem):
        return value

    key = str(value).strip().lower().rstrip(".")
    if key in _ALIASES:
        return _ALIASES[key]

    try:
        return UnitSystem(key)
    except ValueError as exc:
        supported = ", ".join(unit.value for unit in UnitSystem)
        raise ValueError(f"Unsupported unit '{value}'. Supported units: {supported}.") from exc


def to_meters(value: float, unit: UnitSystem | str) -> float:
    return float(value) * METERS_PER_UNIT[parse_unit(unit)]


def from_meters(value: float, unit: UnitSystem | str) -> float:
    return float(value) / METERS_PER_UNIT[parse_unit(unit)]


def convert(value: float, from_unit: UnitSystem | str, to_unit: UnitSystem | str) -> float:
    return from_meters(to_meters(value, from_unit), to_unit)


def feet_to_meters(value: float) -> float:
    return to_meters(value, UnitSystem.FEET)


def meters_to_feet(value: float) -> float:
    return from_meters(value, UnitSystem.FEET)
