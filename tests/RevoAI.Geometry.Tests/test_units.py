from __future__ import annotations

import math

import pytest

from revoai_geometry.units import (
    METERS_PER_FOOT,
    REVIT_INTERNAL_UNIT,
    UnitSystem,
    convert,
    feet_to_meters,
    from_meters,
    meters_to_feet,
    parse_unit,
    to_meters,
)


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("mm", UnitSystem.MILLIMETERS),
        ("CM", UnitSystem.CENTIMETERS),
        ("m", UnitSystem.METERS),
        ("metre", UnitSystem.METERS),
        ("in", UnitSystem.INCHES),
        ("ft", UnitSystem.FEET),
        ("feet", UnitSystem.FEET),
        ("feet.", UnitSystem.FEET),
    ],
)
def test_parse_unit_accepts_common_aliases(alias: str, expected: UnitSystem) -> None:
    assert parse_unit(alias) is expected


def test_unknown_unit_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported unit"):
        parse_unit("cubits")


def test_metre_is_canonical_engine_unit() -> None:
    assert to_meters(1000, "mm") == pytest.approx(1.0)
    assert to_meters(100, "cm") == pytest.approx(1.0)
    assert to_meters(1, "m") == pytest.approx(1.0)
    assert to_meters(12, "in") == pytest.approx(0.3048)


def test_revit_internal_unit_is_feet() -> None:
    assert REVIT_INTERNAL_UNIT is UnitSystem.FEET
    assert METERS_PER_FOOT == pytest.approx(0.3048)


def test_feet_round_trip() -> None:
    assert feet_to_meters(10) == pytest.approx(3.048)
    assert meters_to_feet(3.048) == pytest.approx(10)


def test_convert_between_units() -> None:
    assert convert(3.048, "m", "ft") == pytest.approx(10)
    assert convert(10, "ft", "mm") == pytest.approx(3048)


def test_from_meters_is_inverse_of_to_meters() -> None:
    for unit in UnitSystem:
        value = 2.5
        assert from_meters(to_meters(value, unit), unit) == pytest.approx(value)


def test_nan_is_preserved_not_silently_fixed() -> None:
    assert math.isnan(to_meters(float("nan"), "m"))
