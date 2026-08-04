from __future__ import annotations


REPAIRABLE = {
    "program_schema_invalid",
    "python_syntax_error",
    "execution_failed",
    "timed_out",
    "resource_exhausted",
    "required_output_missing",
    "output_rejected",
    "manifest_invalid",
    "source_mapping_mismatch",
    "semantic_mismatch",
    "required_sections_missing",
    "required_tables_missing",
    "quality_table_invalid",
    "solution_labels_missing",
    "native_math_missing",
    "render_failed",
    "render_page_count",
    "render_empty_page",
    "missing_core_part",
    "invalid_docx_package",
}

NON_REPAIRABLE = {
    "policy_rejected",
    "network_attempt",
    "secret_access_attempt",
    "archive_bomb",
    "embedded_executable",
    "external_relationship",
    "macro_content",
    "unsafe_archive_path",
    "symlink_part",
}


class DocxRepairPolicy:
    def may_repair(self, report) -> bool:
        errors = [item for item in report.issues if item.severity == "error"]
        return bool(errors) and all(
            item.repairable and item.code in REPAIRABLE and item.code not in NON_REPAIRABLE
            for item in errors
        )
