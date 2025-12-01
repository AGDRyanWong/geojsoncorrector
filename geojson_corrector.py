"""
GeoJSON Corrector Backend Module

This module provides functionality to correct invalid GeoJSON geometries
and fix common property type issues.

Uses Shapely's make_valid() to fix geometry issues like:
- Self-intersections
- Invalid polygon rings
- Unclosed rings
- Duplicate points
"""

import json
import re
from typing import Any, Callable
from dataclasses import dataclass, field

from shapely import make_valid
from shapely.geometry import shape, mapping
from shapely.validation import explain_validity


@dataclass
class CorrectionResult:
    """Result of a GeoJSON correction operation."""
    original_feature_count: int = 0
    corrected_feature_count: int = 0
    geometry_issues_fixed: int = 0
    property_issues_fixed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)


class PropertyCorrector:
    """
    Handles correction of property values in GeoJSON features.

    Follows Open/Closed principle - new corrections can be added
    by registering additional correction functions.
    """

    def __init__(self):
        self._corrections: list[tuple[str, Callable[[str, Any], tuple[Any, bool]]]] = []
        self._register_default_corrections()

    def _register_default_corrections(self) -> None:
        """Register built-in property corrections."""
        self.register_correction("numeric_string", self._fix_numeric_string)
        self.register_correction("null_string", self._fix_null_string)
        self.register_correction("boolean_string", self._fix_boolean_string)
        self.register_correction("whitespace", self._fix_whitespace)

    def register_correction(
        self,
        name: str,
        func: Callable[[str, Any], tuple[Any, bool]]
    ) -> None:
        """
        Register a new property correction function.

        Args:
            name: Identifier for the correction type
            func: Function taking (key, value) and returning (corrected_value, was_corrected)
        """
        self._corrections.append((name, func))

    def _fix_numeric_string(self, key: str, value: Any) -> tuple[Any, bool]:
        """Convert string representations of numbers to actual numbers."""
        if not isinstance(value, str):
            return value, False

        stripped = value.strip()

        # Check for integer
        if re.match(r'^-?\d+$', stripped):
            return int(stripped), True

        # Check for float (including scientific notation)
        if re.match(r'^-?\d*\.?\d+(?:[eE][+-]?\d+)?$', stripped):
            return float(stripped), True

        return value, False

    def _fix_null_string(self, key: str, value: Any) -> tuple[Any, bool]:
        """Convert string 'null', 'None', etc. to actual None."""
        if isinstance(value, str) and value.strip().lower() in ('null', 'none', 'nil', ''):
            return None, True
        return value, False

    def _fix_boolean_string(self, key: str, value: Any) -> tuple[Any, bool]:
        """Convert string 'true'/'false' to actual booleans."""
        if isinstance(value, str):
            lower = value.strip().lower()
            if lower == 'true':
                return True, True
            if lower == 'false':
                return False, True
        return value, False

    def _fix_whitespace(self, key: str, value: Any) -> tuple[Any, bool]:
        """Strip excessive whitespace from string values."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped != value:
                return stripped, True
        return value, False

    def correct_properties(
        self,
        properties: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, int]:
        """
        Apply all registered corrections to a properties dict.

        Args:
            properties: The properties dictionary from a GeoJSON feature

        Returns:
            Tuple of (corrected_properties, number_of_fixes)
        """
        if properties is None:
            return None, 0

        corrected = {}
        total_fixes = 0

        for key, value in properties.items():
            current_value = value

            for correction_name, correction_func in self._corrections:
                new_value, was_corrected = correction_func(key, current_value)
                if was_corrected:
                    current_value = new_value
                    total_fixes += 1

            corrected[key] = current_value

        return corrected, total_fixes


class GeometryCorrector:
    """
    Handles validation and correction of GeoJSON geometries using Shapely.
    """

    @staticmethod
    def validate_geometry(geometry: dict[str, Any]) -> tuple[bool, str]:
        """
        Check if a geometry is valid.

        Args:
            geometry: GeoJSON geometry dict

        Returns:
            Tuple of (is_valid, explanation)
        """
        try:
            geom = shape(geometry)
            if geom.is_valid:
                return True, "Valid"
            return False, explain_validity(geom)
        except Exception as e:
            return False, str(e)

    @staticmethod
    def correct_geometry(geometry: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
        """
        Attempt to correct an invalid geometry.

        Args:
            geometry: GeoJSON geometry dict

        Returns:
            Tuple of (corrected_geometry, was_corrected, message)
        """
        try:
            geom = shape(geometry)

            if geom.is_valid:
                return geometry, False, "Geometry was already valid"

            original_issue = explain_validity(geom)
            corrected_geom = make_valid(geom)

            if corrected_geom.is_valid:
                return mapping(corrected_geom), True, f"Fixed: {original_issue}"

            return geometry, False, f"Could not fix: {original_issue}"

        except Exception as e:
            return geometry, False, f"Error processing geometry: {e}"


class GeoJSONCorrector:
    """
    Main class for correcting GeoJSON files.

    Coordinates geometry and property correction using composition.
    """

    def __init__(self):
        self.geometry_corrector = GeometryCorrector()
        self.property_corrector = PropertyCorrector()

    def correct_feature(
        self,
        feature: dict[str, Any],
        feature_index: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Correct a single GeoJSON feature.

        Args:
            feature: GeoJSON feature dict
            feature_index: Index of the feature in the collection

        Returns:
            Tuple of (corrected_feature, correction_details)
        """
        details = {
            "feature_index": feature_index,
            "geometry_corrected": False,
            "geometry_message": "",
            "properties_fixes": 0
        }

        corrected_feature = {
            "type": "Feature",
            "properties": feature.get("properties"),
            "geometry": feature.get("geometry")
        }

        # Preserve other top-level properties (id, bbox, etc.)
        for key in feature:
            if key not in ("type", "properties", "geometry"):
                corrected_feature[key] = feature[key]

        # Correct geometry
        geometry = feature.get("geometry")
        if geometry is not None:
            corrected_geom, was_corrected, message = self.geometry_corrector.correct_geometry(geometry)
            corrected_feature["geometry"] = corrected_geom
            details["geometry_corrected"] = was_corrected
            details["geometry_message"] = message

        # Correct properties
        properties = feature.get("properties")
        corrected_props, prop_fixes = self.property_corrector.correct_properties(properties)
        corrected_feature["properties"] = corrected_props
        details["properties_fixes"] = prop_fixes

        return corrected_feature, details

    def correct_geojson(self, geojson_data: dict[str, Any]) -> tuple[dict[str, Any], CorrectionResult]:
        """
        Correct an entire GeoJSON object.

        Handles both FeatureCollection and single Feature/Geometry types.

        Args:
            geojson_data: Parsed GeoJSON dict

        Returns:
            Tuple of (corrected_geojson, correction_result)
        """
        result = CorrectionResult()

        geojson_type = geojson_data.get("type")

        if geojson_type == "FeatureCollection":
            return self._correct_feature_collection(geojson_data, result)
        elif geojson_type == "Feature":
            return self._correct_single_feature(geojson_data, result)
        elif geojson_type in ("Point", "MultiPoint", "LineString", "MultiLineString",
                              "Polygon", "MultiPolygon", "GeometryCollection"):
            return self._correct_bare_geometry(geojson_data, result)
        else:
            result.errors.append(f"Unknown GeoJSON type: {geojson_type}")
            return geojson_data, result

    def _correct_feature_collection(
        self,
        geojson_data: dict[str, Any],
        result: CorrectionResult
    ) -> tuple[dict[str, Any], CorrectionResult]:
        """Correct a FeatureCollection."""
        features = geojson_data.get("features", [])
        result.original_feature_count = len(features)

        corrected_features = []

        for idx, feature in enumerate(features):
            try:
                corrected_feature, details = self.correct_feature(feature, idx)
                corrected_features.append(corrected_feature)
                result.details.append(details)

                if details["geometry_corrected"]:
                    result.geometry_issues_fixed += 1
                result.property_issues_fixed += details["properties_fixes"]

            except Exception as e:
                result.errors.append(f"Error processing feature {idx}: {e}")
                corrected_features.append(feature)  # Keep original on error

        result.corrected_feature_count = len(corrected_features)

        corrected_geojson = {
            "type": "FeatureCollection",
            "features": corrected_features
        }

        # Preserve other top-level properties (name, crs, bbox, etc.)
        for key in geojson_data:
            if key not in ("type", "features"):
                corrected_geojson[key] = geojson_data[key]

        return corrected_geojson, result

    def _correct_single_feature(
        self,
        geojson_data: dict[str, Any],
        result: CorrectionResult
    ) -> tuple[dict[str, Any], CorrectionResult]:
        """Correct a single Feature."""
        result.original_feature_count = 1

        try:
            corrected_feature, details = self.correct_feature(geojson_data, 0)
            result.details.append(details)

            if details["geometry_corrected"]:
                result.geometry_issues_fixed += 1
            result.property_issues_fixed += details["properties_fixes"]
            result.corrected_feature_count = 1

            return corrected_feature, result

        except Exception as e:
            result.errors.append(f"Error processing feature: {e}")
            return geojson_data, result

    def _correct_bare_geometry(
        self,
        geojson_data: dict[str, Any],
        result: CorrectionResult
    ) -> tuple[dict[str, Any], CorrectionResult]:
        """Correct a bare geometry (not wrapped in a Feature)."""
        result.original_feature_count = 1

        try:
            corrected_geom, was_corrected, message = self.geometry_corrector.correct_geometry(geojson_data)

            if was_corrected:
                result.geometry_issues_fixed = 1

            result.details.append({
                "feature_index": 0,
                "geometry_corrected": was_corrected,
                "geometry_message": message,
                "properties_fixes": 0
            })
            result.corrected_feature_count = 1

            return corrected_geom, result

        except Exception as e:
            result.errors.append(f"Error processing geometry: {e}")
            return geojson_data, result


def correct_geojson_file(file_content: str | bytes) -> tuple[str, CorrectionResult]:
    """
    Convenience function to correct a GeoJSON file from string/bytes content.

    Args:
        file_content: Raw GeoJSON content as string or bytes

    Returns:
        Tuple of (corrected_geojson_string, correction_result)
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode('utf-8')

    result = CorrectionResult()

    try:
        geojson_data = json.loads(file_content)
    except json.JSONDecodeError as e:
        result.errors.append(f"Invalid JSON: {e}")
        return file_content, result

    corrector = GeoJSONCorrector()
    corrected_data, result = corrector.correct_geojson(geojson_data)

    corrected_json = json.dumps(corrected_data, indent=2)

    return corrected_json, result


def validate_geojson_file(file_content: str | bytes) -> list[dict[str, Any]]:
    """
    Validate a GeoJSON file and return issues found.

    Args:
        file_content: Raw GeoJSON content

    Returns:
        List of validation issues with details
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode('utf-8')

    issues = []

    try:
        geojson_data = json.loads(file_content)
    except json.JSONDecodeError as e:
        return [{"type": "json_error", "message": str(e)}]

    geojson_type = geojson_data.get("type")

    if geojson_type == "FeatureCollection":
        features = geojson_data.get("features", [])
        for idx, feature in enumerate(features):
            geometry = feature.get("geometry")
            if geometry:
                is_valid, explanation = GeometryCorrector.validate_geometry(geometry)
                if not is_valid:
                    issues.append({
                        "type": "geometry_invalid",
                        "feature_index": idx,
                        "message": explanation
                    })
    elif geojson_type == "Feature":
        geometry = geojson_data.get("geometry")
        if geometry:
            is_valid, explanation = GeometryCorrector.validate_geometry(geometry)
            if not is_valid:
                issues.append({
                    "type": "geometry_invalid",
                    "feature_index": 0,
                    "message": explanation
                })
    elif geojson_type in ("Point", "MultiPoint", "LineString", "MultiLineString",
                          "Polygon", "MultiPolygon", "GeometryCollection"):
        is_valid, explanation = GeometryCorrector.validate_geometry(geojson_data)
        if not is_valid:
            issues.append({
                "type": "geometry_invalid",
                "feature_index": 0,
                "message": explanation
            })

    return issues
