"""
GeoJSON Corrector Streamlit Application

A web interface for validating and correcting GeoJSON files.
"""

import json
import streamlit as st
from geojson_corrector import correct_geojson_file, validate_geojson_file, CorrectionResult


def display_correction_result(result: CorrectionResult) -> None:
    """Display the correction results in a user-friendly format."""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Features Processed", result.original_feature_count)
    with col2:
        st.metric("Geometry Issues Fixed", result.geometry_issues_fixed)
    with col3:
        st.metric("Property Issues Fixed", result.property_issues_fixed)

    if result.errors:
        st.error("Errors encountered:")
        for error in result.errors:
            st.write(f"- {error}")

    if result.warnings:
        st.warning("Warnings:")
        for warning in result.warnings:
            st.write(f"- {warning}")

    if result.details:
        with st.expander("View detailed corrections"):
            for detail in result.details:
                if detail.get("geometry_corrected") or detail.get("properties_fixes", 0) > 0:
                    st.write(f"**Feature {detail['feature_index']}:**")
                    if detail.get("geometry_corrected"):
                        st.write(f"  - Geometry: {detail['geometry_message']}")
                    if detail.get("properties_fixes", 0) > 0:
                        st.write(f"  - Properties fixed: {detail['properties_fixes']}")


def main():
    st.set_page_config(
        page_title="GeoJSON Corrector",
        page_icon="🗺️",
        layout="wide"
    )

    st.title("GeoJSON Corrector")
    st.markdown("""
    Upload a GeoJSON file to validate and correct common issues:
    - **Geometry issues**: Self-intersections, invalid rings, unclosed polygons
    - **Property issues**: String numbers converted to actual numbers, null strings, boolean strings
    """)

    uploaded_file = st.file_uploader(
        "Upload GeoJSON file",
        type=["geojson", "json"],
        help="Select a .geojson or .json file"
    )

    if uploaded_file is not None:
        file_content = uploaded_file.read()

        st.subheader("Validation Results")

        issues = validate_geojson_file(file_content)

        if not issues:
            st.success("No geometry issues detected in the original file.")
        else:
            st.warning(f"Found {len(issues)} geometry issue(s):")
            for issue in issues[:10]:  # Show first 10
                st.write(f"- Feature {issue.get('feature_index', 'N/A')}: {issue['message']}")
            if len(issues) > 10:
                st.write(f"... and {len(issues) - 10} more issues")

        st.subheader("Correction")

        if st.button("Correct GeoJSON", type="primary"):
            with st.spinner("Correcting GeoJSON..."):
                corrected_json, result = correct_geojson_file(file_content)

            if result.errors:
                st.error("Correction completed with errors.")
            elif result.geometry_issues_fixed > 0 or result.property_issues_fixed > 0:
                st.success("Correction completed successfully!")
            else:
                st.info("No corrections were necessary.")

            display_correction_result(result)

            st.subheader("Download Corrected File")

            original_filename = uploaded_file.name
            if original_filename.endswith('.geojson'):
                corrected_filename = original_filename.replace('.geojson', '_corrected.geojson')
            elif original_filename.endswith('.json'):
                corrected_filename = original_filename.replace('.json', '_corrected.json')
            else:
                corrected_filename = f"{original_filename}_corrected.geojson"

            st.download_button(
                label="Download Corrected GeoJSON",
                data=corrected_json,
                file_name=corrected_filename,
                mime="application/geo+json"
            )

            with st.expander("Preview corrected GeoJSON"):
                try:
                    parsed = json.loads(corrected_json)
                    # Show truncated preview for large files
                    preview_str = json.dumps(parsed, indent=2)
                    if len(preview_str) > 10000:
                        st.code(preview_str[:10000] + "\n... (truncated)", language="json")
                    else:
                        st.code(preview_str, language="json")
                except json.JSONDecodeError:
                    st.code(corrected_json[:5000], language="json")


if __name__ == "__main__":
    main()
