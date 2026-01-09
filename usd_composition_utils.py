"""
USD Scene Composition Utilities

Production utilities for USD layer management, composition arcs,
and scene assembly. Demonstrates common USD patterns for pipelines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from pxr import Sdf, Usd, UsdGeom, UsdShade

if TYPE_CHECKING:
    from collections.abc import Iterator

from crafty_logger import get_logger

LOGGER = get_logger("usd_composition")


class CompositionArcType(Enum):
    """Types of USD composition arcs."""

    SUBLAYER = auto()
    REFERENCE = auto()
    PAYLOAD = auto()
    INHERIT = auto()
    SPECIALIZE = auto()
    VARIANT = auto()


@dataclass
class LayerInfo:
    """Information about a USD layer."""

    identifier: str
    path: Path | None
    is_anonymous: bool
    is_dirty: bool
    sublayer_count: int
    prim_count: int
    default_prim: str | None


@dataclass
class CompositionArc:
    """Represents a composition arc in USD."""

    arc_type: CompositionArcType
    source_path: str
    target_prim: str
    layer_offset: float = 0.0
    layer_scale: float = 1.0


@dataclass
class AssetInfo:
    """USD asset metadata."""

    name: str
    identifier: str
    version: str = ""
    kind: str = ""
    purpose: str = "default"


def get_layer_info(layer: Sdf.Layer) -> LayerInfo:
    """
    Get detailed information about a USD layer.

    Args:
        layer: The USD layer to inspect

    Returns:
        LayerInfo dataclass with layer details
    """
    path = None
    if not layer.anonymous:
        path = Path(layer.realPath) if layer.realPath else None

    prim_count = 0
    for prim in layer.rootPrims:
        prim_count += 1

    return LayerInfo(
        identifier=layer.identifier,
        path=path,
        is_anonymous=layer.anonymous,
        is_dirty=layer.dirty,
        sublayer_count=len(layer.subLayerPaths),
        prim_count=prim_count,
        default_prim=layer.defaultPrim if layer.defaultPrim else None,
    )


def create_assembly_layer(
    output_path: str | Path,
    asset_name: str,
    sublayers: list[str | Path] | None = None,
) -> Sdf.Layer:
    """
    Create a new USD assembly layer with optional sublayers.

    Args:
        output_path: Path for the new layer
        asset_name: Name for the default prim
        sublayers: Optional list of sublayer paths to include

    Returns:
        The created Sdf.Layer
    """
    layer = Sdf.Layer.CreateNew(str(output_path))

    layer.defaultPrim = asset_name

    root_prim = Sdf.CreatePrimInLayer(layer, f"/{asset_name}")
    root_prim.specifier = Sdf.SpecifierDef
    root_prim.typeName = "Xform"

    if sublayers:
        for sublayer_path in sublayers:
            layer.subLayerPaths.append(str(sublayer_path))

    layer.Save()
    LOGGER.info("Created assembly layer: %s", output_path)

    return layer


def add_reference(
    stage: Usd.Stage,
    prim_path: str,
    reference_path: str | Path,
    reference_prim_path: str | None = None,
) -> Usd.Prim:
    """
    Add a reference to a prim.

    Args:
        stage: The USD stage
        prim_path: Path for the prim to add reference to
        reference_path: Path to the referenced file
        reference_prim_path: Optional specific prim path in the reference

    Returns:
        The prim with the added reference
    """
    prim = stage.DefinePrim(prim_path, "Xform")
    references = prim.GetReferences()

    if reference_prim_path:
        references.AddReference(str(reference_path), reference_prim_path)
    else:
        references.AddReference(str(reference_path))

    LOGGER.info("Added reference to %s: %s", prim_path, reference_path)
    return prim


def add_payload(
    stage: Usd.Stage,
    prim_path: str,
    payload_path: str | Path,
    payload_prim_path: str | None = None,
) -> Usd.Prim:
    """
    Add a payload to a prim for deferred loading.

    Args:
        stage: The USD stage
        prim_path: Path for the prim to add payload to
        payload_path: Path to the payload file
        payload_prim_path: Optional specific prim path in the payload

    Returns:
        The prim with the added payload
    """
    prim = stage.DefinePrim(prim_path, "Xform")
    payloads = prim.GetPayloads()

    if payload_prim_path:
        payloads.AddPayload(str(payload_path), payload_prim_path)
    else:
        payloads.AddPayload(str(payload_path))

    LOGGER.info("Added payload to %s: %s", prim_path, payload_path)
    return prim


def create_variant_set(
    prim: Usd.Prim,
    variant_set_name: str,
    variants: dict[str, str | Path],
    default_variant: str | None = None,
) -> Usd.VariantSet:
    """
    Create a variant set with references for each variant.

    Args:
        prim: The prim to add the variant set to
        variant_set_name: Name for the variant set
        variants: Dictionary mapping variant names to asset paths
        default_variant: Optional default variant selection

    Returns:
        The created VariantSet
    """
    variant_set = prim.GetVariantSets().AddVariantSet(variant_set_name)

    for variant_name, asset_path in variants.items():
        variant_set.AddVariant(variant_name)
        variant_set.SetVariantSelection(variant_name)

        with variant_set.GetVariantEditContext():
            prim.GetReferences().AddReference(str(asset_path))

    if default_variant and default_variant in variants:
        variant_set.SetVariantSelection(default_variant)
    elif variants:
        variant_set.SetVariantSelection(next(iter(variants)))

    LOGGER.info("Created variant set '%s' with %d variants", variant_set_name, len(variants))
    return variant_set


def get_composition_arcs(prim: Usd.Prim) -> list[CompositionArc]:
    """
    Get all composition arcs for a prim.

    Args:
        prim: The prim to inspect

    Returns:
        List of CompositionArc objects
    """
    arcs: list[CompositionArc] = []
    prim_index = prim.GetPrimIndex()

    for node in prim_index.nodeRange:
        arc_type_map = {
            Usd.ArcTypeReference: CompositionArcType.REFERENCE,
            Usd.ArcTypePayload: CompositionArcType.PAYLOAD,
            Usd.ArcTypeInherit: CompositionArcType.INHERIT,
            Usd.ArcTypeSpecialize: CompositionArcType.SPECIALIZE,
            Usd.ArcTypeVariant: CompositionArcType.VARIANT,
        }

        if node.arcType in arc_type_map:
            layer = node.GetLayer()
            arcs.append(CompositionArc(
                arc_type=arc_type_map[node.arcType],
                source_path=layer.identifier if layer else "",
                target_prim=str(node.path),
            ))

    return arcs


def flatten_stage(stage: Usd.Stage, output_path: str | Path) -> Sdf.Layer:
    """
    Flatten a composed USD stage to a single layer.

    Args:
        stage: The stage to flatten
        output_path: Path for the flattened layer

    Returns:
        The flattened layer
    """
    flat_layer = stage.Flatten()
    flat_layer.Export(str(output_path))
    LOGGER.info("Flattened stage to: %s", output_path)
    return flat_layer


def traverse_stage(
    stage: Usd.Stage,
    prim_filter: set[str] | None = None,
    include_inactive: bool = False,
) -> Iterator[Usd.Prim]:
    """
    Traverse all prims in a stage.

    Args:
        stage: The USD stage to traverse
        prim_filter: Optional set of prim types to include
        include_inactive: Whether to include inactive prims

    Yields:
        Prims matching the filter criteria
    """
    predicate = Usd.TraverseInstanceProxies()
    if not include_inactive:
        predicate = predicate & Usd.PrimIsActive

    for prim in stage.Traverse(predicate):
        if prim_filter:
            if prim.GetTypeName() in prim_filter:
                yield prim
        else:
            yield prim


def get_all_meshes(stage: Usd.Stage) -> list[UsdGeom.Mesh]:
    """
    Get all mesh prims in a stage.

    Args:
        stage: The USD stage

    Returns:
        List of UsdGeom.Mesh objects
    """
    meshes = []
    for prim in traverse_stage(stage, prim_filter={"Mesh"}):
        mesh = UsdGeom.Mesh(prim)
        if mesh:
            meshes.append(mesh)
    return meshes


def set_asset_info(
    prim: Usd.Prim,
    info: AssetInfo,
) -> None:
    """
    Set USD asset info metadata on a prim.

    Args:
        prim: The prim to set metadata on
        info: AssetInfo with the metadata values
    """
    model = Usd.ModelAPI(prim)

    if info.name:
        model.SetAssetName(info.name)
    if info.identifier:
        model.SetAssetIdentifier(info.identifier)
    if info.version:
        model.SetAssetVersion(info.version)
    if info.kind:
        model.SetKind(info.kind)

    if info.purpose != "default":
        imageable = UsdGeom.Imageable(prim)
        if imageable:
            imageable.GetPurposeAttr().Set(info.purpose)


def create_shot_layer(
    output_path: str | Path,
    shot_name: str,
    sequence_name: str,
    frame_range: tuple[int, int],
    fps: float = 24.0,
) -> Usd.Stage:
    """
    Create a new shot layer with proper stage metadata.

    Args:
        output_path: Path for the shot layer
        shot_name: Name of the shot
        sequence_name: Name of the sequence
        frame_range: Tuple of (start_frame, end_frame)
        fps: Frames per second

    Returns:
        The created stage
    """
    stage = Usd.Stage.CreateNew(str(output_path))

    stage.SetMetadata("comment", f"Shot: {sequence_name}/{shot_name}")
    stage.SetStartTimeCode(frame_range[0])
    stage.SetEndTimeCode(frame_range[1])
    stage.SetTimeCodesPerSecond(fps)
    stage.SetFramesPerSecond(fps)

    root_prim = stage.DefinePrim(f"/{shot_name}", "Xform")
    stage.SetDefaultPrim(root_prim)

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)

    stage.GetRootLayer().Save()
    LOGGER.info("Created shot layer: %s (%d-%d)", output_path, frame_range[0], frame_range[1])

    return stage


def collect_external_references(stage: Usd.Stage) -> set[str]:
    """
    Collect all external file references from a stage.

    Args:
        stage: The USD stage to analyze

    Returns:
        Set of external file paths
    """
    external_refs: set[str] = set()

    for layer in stage.GetUsedLayers():
        external_refs.add(layer.identifier)

        for sublayer_path in layer.subLayerPaths:
            resolved = layer.ComputeAbsolutePath(sublayer_path)
            if resolved:
                external_refs.add(resolved)

    for prim in stage.Traverse():
        for ref in prim.GetReferences().GetAddedItems():
            if ref.assetPath:
                external_refs.add(ref.assetPath)
        for payload in prim.GetPayloads().GetAddedItems():
            if payload.assetPath:
                external_refs.add(payload.assetPath)

    return external_refs
