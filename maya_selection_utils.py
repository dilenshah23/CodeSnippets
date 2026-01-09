"""
Maya Selection Utilities

Production utilities for complex selection operations in Maya,
including filtering, hierarchical selection, and selection sets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import lru_cache
from typing import TYPE_CHECKING

import maya.api.OpenMaya as om
from maya import cmds

if TYPE_CHECKING:
    from collections.abc import Callable

from crafty_logger import get_logger

LOGGER = get_logger("selection_utils")


class SelectionMode(Enum):
    """Selection operation modes."""

    REPLACE = auto()
    ADD = auto()
    REMOVE = auto()
    TOGGLE = auto()


@dataclass
class SelectionFilter:
    """Configuration for filtering selections."""

    node_types: list[str] | None = None
    name_pattern: str | None = None
    exclude_pattern: str | None = None
    namespace: str | None = None
    referenced_only: bool = False
    non_referenced_only: bool = False
    visible_only: bool = False
    custom_filter: Callable[[str], bool] | None = None


@dataclass
class SelectionSnapshot:
    """Snapshot of a selection state for undo/redo."""

    nodes: list[str]
    timestamp: float = field(default_factory=lambda: cmds.timerX())

    def restore(self) -> None:
        """Restore this selection state."""
        cmds.select(self.nodes, replace=True)


class SelectionStack:
    """Stack for tracking selection history."""

    def __init__(self, max_size: int = 50) -> None:
        self._stack: list[SelectionSnapshot] = []
        self._max_size = max_size
        self._index = -1

    def push(self) -> None:
        """Push current selection onto the stack."""
        current = cmds.ls(selection=True, long=True) or []
        snapshot = SelectionSnapshot(nodes=current)

        self._index += 1
        if self._index < len(self._stack):
            self._stack = self._stack[: self._index]
        self._stack.append(snapshot)

        if len(self._stack) > self._max_size:
            self._stack.pop(0)
            self._index -= 1

    def undo(self) -> bool:
        """Restore previous selection from stack."""
        if self._index > 0:
            self._index -= 1
            self._stack[self._index].restore()
            return True
        return False

    def redo(self) -> bool:
        """Restore next selection from stack."""
        if self._index < len(self._stack) - 1:
            self._index += 1
            self._stack[self._index].restore()
            return True
        return False


_selection_stack = SelectionStack()


def get_selection(
    filter_config: SelectionFilter | None = None,
    long_names: bool = True,
) -> list[str]:
    """
    Get the current selection with optional filtering.

    Args:
        filter_config: Optional filter configuration
        long_names: Return full DAG paths

    Returns:
        List of selected node names
    """
    selection = cmds.ls(selection=True, long=long_names) or []

    if filter_config:
        selection = apply_filter(selection, filter_config)

    return selection


def apply_filter(nodes: list[str], config: SelectionFilter) -> list[str]:
    """
    Apply a filter to a list of nodes.

    Args:
        nodes: List of node names
        config: Filter configuration

    Returns:
        Filtered list of nodes
    """
    result = nodes.copy()

    if config.node_types:
        result = [n for n in result if cmds.nodeType(n) in config.node_types]

    if config.name_pattern:
        pattern = re.compile(config.name_pattern)
        result = [n for n in result if pattern.search(n.split("|")[-1])]

    if config.exclude_pattern:
        exclude = re.compile(config.exclude_pattern)
        result = [n for n in result if not exclude.search(n.split("|")[-1])]

    if config.namespace:
        ns_prefix = f"{config.namespace}:"
        result = [n for n in result if ns_prefix in n]

    if config.referenced_only:
        result = [n for n in result if cmds.referenceQuery(n, isNodeReferenced=True)]

    if config.non_referenced_only:
        result = [n for n in result if not cmds.referenceQuery(n, isNodeReferenced=True)]

    if config.visible_only:
        result = [n for n in result if _is_visible(n)]

    if config.custom_filter:
        result = [n for n in result if config.custom_filter(n)]

    return result


def _is_visible(node: str) -> bool:
    """Check if a node and all its parents are visible."""
    try:
        if not cmds.getAttr(f"{node}.visibility"):
            return False

        parents = cmds.listRelatives(node, allParents=True, fullPath=True) or []
        for parent in parents:
            if cmds.attributeQuery("visibility", node=parent, exists=True):
                if not cmds.getAttr(f"{parent}.visibility"):
                    return False
        return True
    except ValueError:
        return True


def select_hierarchy(
    root_nodes: list[str] | None = None,
    include_root: bool = True,
    filter_config: SelectionFilter | None = None,
    mode: SelectionMode = SelectionMode.REPLACE,
) -> list[str]:
    """
    Select all descendants of the given nodes.

    Args:
        root_nodes: Root nodes to select from (uses selection if None)
        include_root: Include root nodes in selection
        filter_config: Optional filter for the selection
        mode: Selection mode

    Returns:
        List of selected nodes
    """
    if root_nodes is None:
        root_nodes = cmds.ls(selection=True, long=True) or []

    if not root_nodes:
        return []

    all_descendants: list[str] = []

    for root in root_nodes:
        if include_root:
            all_descendants.append(root)
        descendants = cmds.listRelatives(root, allDescendents=True, fullPath=True) or []
        all_descendants.extend(descendants)

    if filter_config:
        all_descendants = apply_filter(all_descendants, filter_config)

    _apply_selection(all_descendants, mode)
    return all_descendants


def select_by_type(
    node_types: list[str],
    scope: list[str] | None = None,
    mode: SelectionMode = SelectionMode.REPLACE,
) -> list[str]:
    """
    Select nodes by type, optionally within a scope.

    Args:
        node_types: List of node types to select
        scope: Optional list of nodes to search within
        mode: Selection mode

    Returns:
        List of selected nodes
    """
    if scope:
        nodes = []
        for root in scope:
            for node_type in node_types:
                found = cmds.listRelatives(
                    root, allDescendents=True, type=node_type, fullPath=True
                ) or []
                nodes.extend(found)
    else:
        nodes = cmds.ls(type=node_types, long=True) or []

    _apply_selection(nodes, mode)
    return nodes


def select_by_attribute(
    attribute_name: str,
    value: float | int | str | bool | None = None,
    comparison: str = "==",
    scope: list[str] | None = None,
    mode: SelectionMode = SelectionMode.REPLACE,
) -> list[str]:
    """
    Select nodes that have a specific attribute value.

    Args:
        attribute_name: Name of the attribute
        value: Value to compare (None means attribute just needs to exist)
        comparison: Comparison operator (==, !=, <, >, <=, >=)
        scope: Optional list of nodes to search
        mode: Selection mode

    Returns:
        List of selected nodes
    """
    search_nodes = scope if scope else cmds.ls(dag=True, long=True)
    matching: list[str] = []

    for node in search_nodes:
        if not cmds.attributeQuery(attribute_name, node=node, exists=True):
            continue

        if value is None:
            matching.append(node)
            continue

        attr_value = cmds.getAttr(f"{node}.{attribute_name}")

        if _compare_values(attr_value, value, comparison):
            matching.append(node)

    _apply_selection(matching, mode)
    return matching


def _compare_values(a: float | int | str | bool, b: float | int | str | bool, op: str) -> bool:
    """Compare two values using the specified operator."""
    comparisons = {
        "==": lambda x, y: x == y,
        "!=": lambda x, y: x != y,
        "<": lambda x, y: x < y,
        ">": lambda x, y: x > y,
        "<=": lambda x, y: x <= y,
        ">=": lambda x, y: x >= y,
    }
    return comparisons.get(op, comparisons["=="])(a, b)


def _apply_selection(nodes: list[str], mode: SelectionMode) -> None:
    """Apply selection with the specified mode."""
    if not nodes:
        return

    _selection_stack.push()

    if mode == SelectionMode.REPLACE:
        cmds.select(nodes, replace=True)
    elif mode == SelectionMode.ADD:
        cmds.select(nodes, add=True)
    elif mode == SelectionMode.REMOVE:
        cmds.select(nodes, deselect=True)
    elif mode == SelectionMode.TOGGLE:
        cmds.select(nodes, toggle=True)


def select_similar(
    reference_nodes: list[str] | None = None,
    match_type: bool = True,
    match_shape_type: bool = False,
    match_material: bool = False,
) -> list[str]:
    """
    Select nodes similar to the reference nodes.

    Args:
        reference_nodes: Reference nodes (uses selection if None)
        match_type: Match by node type
        match_shape_type: Match by shape node type
        match_material: Match by assigned material

    Returns:
        List of similar nodes
    """
    if reference_nodes is None:
        reference_nodes = cmds.ls(selection=True, long=True) or []

    if not reference_nodes:
        return []

    ref_types: set[str] = set()
    ref_shape_types: set[str] = set()
    ref_materials: set[str] = set()

    for node in reference_nodes:
        if match_type:
            ref_types.add(cmds.nodeType(node))

        if match_shape_type:
            shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
            for shape in shapes:
                ref_shape_types.add(cmds.nodeType(shape))

        if match_material:
            materials = _get_assigned_materials(node)
            ref_materials.update(materials)

    all_transforms = cmds.ls(transforms=True, long=True) or []
    matching: list[str] = []

    for transform in all_transforms:
        if transform in reference_nodes:
            continue

        matches = True

        if match_type and cmds.nodeType(transform) not in ref_types:
            matches = False

        if matches and match_shape_type:
            shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
            shape_types = {cmds.nodeType(s) for s in shapes}
            if not shape_types.intersection(ref_shape_types):
                matches = False

        if matches and match_material:
            materials = _get_assigned_materials(transform)
            if not set(materials).intersection(ref_materials):
                matches = False

        if matches:
            matching.append(transform)

    cmds.select(reference_nodes + matching, replace=True)
    return matching


def _get_assigned_materials(node: str) -> list[str]:
    """Get materials assigned to a node."""
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    materials: list[str] = []

    for shape in shapes:
        shading_engines = cmds.listConnections(shape, type="shadingEngine") or []
        for sg in shading_engines:
            surface_shader = cmds.listConnections(f"{sg}.surfaceShader") or []
            materials.extend(surface_shader)

    return list(set(materials))


def grow_selection(steps: int = 1) -> list[str]:
    """
    Grow selection to include connected components.

    Args:
        steps: Number of times to grow selection

    Returns:
        New selection list
    """
    for _ in range(steps):
        cmds.select(cmds.polyListComponentConversion(toVertex=True))
        cmds.select(cmds.polyListComponentConversion(toFace=True))

    return cmds.ls(selection=True, flatten=True) or []


def shrink_selection(steps: int = 1) -> list[str]:
    """
    Shrink selection by removing boundary components.

    Args:
        steps: Number of times to shrink selection

    Returns:
        New selection list
    """
    for _ in range(steps):
        cmds.ConvertSelectionToContainedFaces()

    return cmds.ls(selection=True, flatten=True) or []


def selection_to_set(set_name: str, nodes: list[str] | None = None) -> str:
    """
    Create a selection set from nodes.

    Args:
        set_name: Name for the selection set
        nodes: Nodes to add (uses selection if None)

    Returns:
        Name of the created set
    """
    if nodes is None:
        nodes = cmds.ls(selection=True, long=True) or []

    if cmds.objExists(set_name):
        cmds.delete(set_name)

    selection_set = cmds.sets(nodes, name=set_name)
    LOGGER.info("Created selection set '%s' with %d members", set_name, len(nodes))
    return selection_set


def set_to_selection(set_name: str) -> list[str]:
    """
    Select all members of a selection set.

    Args:
        set_name: Name of the selection set

    Returns:
        List of selected nodes
    """
    if not cmds.objExists(set_name):
        LOGGER.warning("Selection set does not exist: %s", set_name)
        return []

    members = cmds.sets(set_name, query=True) or []
    cmds.select(members, replace=True)
    return members


def undo_selection() -> bool:
    """Undo to previous selection state."""
    return _selection_stack.undo()


def redo_selection() -> bool:
    """Redo to next selection state."""
    return _selection_stack.redo()
