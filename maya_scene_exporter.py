"""
Maya Scene Exporter Utility

A production-ready scene exporter demonstrating Maya API usage,
validation workflows, and proper error handling patterns.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from maya import cmds

if TYPE_CHECKING:
    from collections.abc import Callable

from crafty_logger import get_logger

LOGGER = get_logger("scene_exporter")

SUPPORTED_FORMATS = {
    ".ma": "mayaAscii",
    ".mb": "mayaBinary",
    ".fbx": "FBX export",
    ".abc": "Alembic",
    ".usd": "USD Export",
}


@dataclass
class ExportConfig:
    """Configuration for scene export operations."""

    output_path: Path
    format_type: str
    frame_range: tuple[int, int] | None = None
    selected_only: bool = False
    include_references: bool = True
    validators: list[Callable[[], bool]] = field(default_factory=list)


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    output_path: Path | None
    duration_seconds: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SceneValidator:
    """Collection of scene validation checks."""

    @staticmethod
    def check_unsaved_changes() -> bool:
        """Verify scene has no unsaved changes."""
        if cmds.file(query=True, modified=True):
            LOGGER.warning("Scene has unsaved changes")
            return False
        return True

    @staticmethod
    def check_unknown_nodes() -> bool:
        """Check for unknown node types that may cause issues."""
        unknown_nodes = cmds.ls(type="unknown") or []
        if unknown_nodes:
            LOGGER.warning("Found %d unknown nodes: %s", len(unknown_nodes), unknown_nodes[:5])
            return False
        return True

    @staticmethod
    def check_broken_references() -> bool:
        """Verify all references are valid and loaded."""
        references = cmds.file(query=True, reference=True) or []
        for ref in references:
            try:
                if not cmds.referenceQuery(ref, isLoaded=True):
                    LOGGER.warning("Unloaded reference: %s", ref)
                    return False
            except RuntimeError as e:
                LOGGER.error("Broken reference: %s - %s", ref, e)
                return False
        return True

    @staticmethod
    def check_duplicate_names() -> bool:
        """Check for duplicate object names in the scene."""
        all_objects = cmds.ls(dag=True, long=True) or []
        short_names = [obj.split("|")[-1] for obj in all_objects]
        duplicates = [name for name in set(short_names) if short_names.count(name) > 1]
        if duplicates:
            LOGGER.warning("Found duplicate names: %s", duplicates[:10])
            return False
        return True


class SceneExporter:
    """Handles Maya scene export operations with validation and logging."""

    def __init__(self, config: ExportConfig) -> None:
        self.config = config
        self._start_time: datetime | None = None

    def export(self) -> ExportResult:
        """
        Execute the export operation with validation.

        Returns:
            ExportResult containing success status and metadata
        """
        self._start_time = datetime.now()
        errors: list[str] = []
        warnings: list[str] = []

        if not self._validate_config():
            return self._create_result(False, errors=["Invalid export configuration"])

        validation_passed, validation_errors = self._run_validators()
        if not validation_passed:
            errors.extend(validation_errors)
            return self._create_result(False, errors=errors)

        try:
            self._ensure_output_directory()
            self._execute_export()
            LOGGER.info("Export completed: %s", self.config.output_path)
            return self._create_result(True, warnings=warnings)
        except RuntimeError as e:
            LOGGER.exception(e)
            errors.append(str(e))
            return self._create_result(False, errors=errors)

    def _validate_config(self) -> bool:
        """Validate export configuration."""
        suffix = self.config.output_path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            LOGGER.error("Unsupported format: %s", suffix)
            return False
        return True

    def _run_validators(self) -> tuple[bool, list[str]]:
        """Run all configured validators."""
        errors: list[str] = []
        for validator in self.config.validators:
            try:
                if not validator():
                    errors.append(f"Validation failed: {validator.__name__}")
            except Exception as e:
                LOGGER.exception(e)
                errors.append(f"Validator error: {validator.__name__} - {e}")
        return len(errors) == 0, errors

    def _ensure_output_directory(self) -> None:
        """Create output directory if it doesn't exist."""
        self.config.output_path.parent.mkdir(parents=True, exist_ok=True)

    def _execute_export(self) -> None:
        """Execute the appropriate export based on format."""
        suffix = self.config.output_path.suffix.lower()
        export_type = SUPPORTED_FORMATS[suffix]

        export_kwargs = {
            "force": True,
            "type": export_type,
        }

        if self.config.selected_only:
            export_kwargs["exportSelected"] = True
            cmds.file(str(self.config.output_path), **export_kwargs)
        else:
            export_kwargs["exportAll"] = True
            cmds.file(str(self.config.output_path), **export_kwargs)

    def _create_result(
        self,
        success: bool,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> ExportResult:
        """Create an ExportResult with timing information."""
        duration = 0.0
        if self._start_time:
            duration = (datetime.now() - self._start_time).total_seconds()

        return ExportResult(
            success=success,
            output_path=self.config.output_path if success else None,
            duration_seconds=duration,
            errors=errors or [],
            warnings=warnings or [],
        )


def export_scene(
    output_path: str | Path,
    selected_only: bool = False,
    validate: bool = True,
) -> ExportResult:
    """
    Export the current Maya scene with optional validation.

    Args:
        output_path: Destination path for the exported file
        selected_only: Export only selected objects
        validate: Run validation checks before export

    Returns:
        ExportResult with export status and metadata
    """
    validators = []
    if validate:
        validators = [
            SceneValidator.check_unsaved_changes,
            SceneValidator.check_unknown_nodes,
            SceneValidator.check_broken_references,
            SceneValidator.check_duplicate_names,
        ]

    config = ExportConfig(
        output_path=Path(output_path),
        format_type=SUPPORTED_FORMATS.get(Path(output_path).suffix.lower(), "mayaAscii"),
        selected_only=selected_only,
        validators=validators,
    )

    exporter = SceneExporter(config)
    return exporter.export()


def batch_export_references(
    output_directory: str | Path,
    format_suffix: str = ".ma",
) -> dict[str, ExportResult]:
    """
    Export all referenced files as individual scenes.

    Args:
        output_directory: Directory to save exported files
        format_suffix: File format extension

    Returns:
        Dictionary mapping reference names to their ExportResult
    """
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, ExportResult] = {}
    references = cmds.file(query=True, reference=True) or []

    for ref_path in references:
        ref_node = cmds.referenceQuery(ref_path, referenceNode=True)
        ref_namespace = cmds.referenceQuery(ref_path, namespace=True).lstrip(":")

        output_path = output_dir / f"{ref_namespace}{format_suffix}"

        cmds.select(clear=True)
        ref_objects = cmds.referenceQuery(ref_path, nodes=True) or []
        if ref_objects:
            cmds.select(ref_objects)
            results[ref_namespace] = export_scene(output_path, selected_only=True, validate=False)
        else:
            results[ref_namespace] = ExportResult(
                success=False,
                output_path=None,
                duration_seconds=0.0,
                errors=[f"No objects found in reference: {ref_namespace}"],
            )

    return results
