"""Revo AI BIM geometry kernel.

Phase 1 provides the unit system foundation that every later stage depends on:
scan units, engine units (metres) and Revit internal units (feet).
"""

from .units import (
    METERS_PER_UNIT,
    REVIT_INTERNAL_UNIT,
    UnitSystem,
    convert,
    feet_to_meters,
    from_meters,
    meters_to_feet,
    parse_unit,
    to_meters,
)

__version__ = "0.2.0"

__all__ = [
    "METERS_PER_UNIT",
    "REVIT_INTERNAL_UNIT",
    "UnitSystem",
    "convert",
    "feet_to_meters",
    "from_meters",
    "meters_to_feet",
    "parse_unit",
    "to_meters",
]
