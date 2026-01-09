"""
Maya Node Graph Traversal Utilities

Production utilities for traversing and analyzing Maya's dependency graph.
Demonstrates both cmds and OpenMaya approaches for node relationships.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

import maya.api.OpenMaya as om
from maya import cmds

if TYPE_CHECKING:
    from collections.abc import Iterator

from crafty_logger import get_logger

LOGGER = get_logger("node_graph")


class TraversalDirection(Enum):
    """Direction for graph traversal."""

    UPSTREAM = auto()
    DOWNSTREAM = auto()
    BOTH = auto()


@dataclass
class NodeInfo:
    """Information about a Maya node."""

    name: str
    node_type: str
    is_referenced: bool
    namespace: str
    connections_in: list[str] = field(default_factory=list)
    connections_out: list[str] = field(default_factory=list)


@dataclass
class ConnectionInfo:
    """Information about a node connection."""

    source_node: str
    source_attr: str
    dest_node: str
    dest_attr: str


def get_node_info(node: str) -> NodeInfo | None:
    """
    Get detailed information about a node.

    Args:
        node: Name of the Maya node

    Returns:
        NodeInfo dataclass or None if node doesn't exist
    """
    if not cmds.objExists(node):
        LOGGER.warning("Node does not exist: %s", node)
        return None

    node_type = cmds.nodeType(node)
    is_referenced = cmds.referenceQuery(node, isNodeReferenced=True)

    namespace = ""
    if ":" in node:
        namespace = node.rsplit(":", 1)[0]

    connections_in = cmds.listConnections(node, source=True, destination=False, plugs=False) or []
    connections_out = cmds.listConnections(node, source=False, destination=True, plugs=False) or []

    return NodeInfo(
        name=node,
        node_type=node_type,
        is_referenced=is_referenced,
        namespace=namespace,
        connections_in=list(set(connections_in)),
        connections_out=list(set(connections_out)),
    )


def get_all_connections(node: str) -> list[ConnectionInfo]:
    """
    Get all input and output connections for a node.

    Args:
        node: Name of the Maya node

    Returns:
        List of ConnectionInfo objects
    """
    connections: list[ConnectionInfo] = []

    if not cmds.objExists(node):
        return connections

    plugs = cmds.listConnections(node, connections=True, plugs=True) or []

    for i in range(0, len(plugs), 2):
        plug_a = plugs[i]
        plug_b = plugs[i + 1]

        node_a, attr_a = plug_a.split(".", 1)
        node_b, attr_b = plug_b.split(".", 1)

        if node_a == node:
            connections.append(ConnectionInfo(
                source_node=node_b,
                source_attr=attr_b,
                dest_node=node_a,
                dest_attr=attr_a,
            ))
        else:
            connections.append(ConnectionInfo(
                source_node=node_a,
                source_attr=attr_a,
                dest_node=node_b,
                dest_attr=attr_b,
            ))

    return connections


def traverse_graph(
    start_node: str,
    direction: TraversalDirection = TraversalDirection.UPSTREAM,
    max_depth: int = -1,
    node_filter: set[str] | None = None,
) -> Iterator[tuple[str, int]]:
    """
    Traverse the dependency graph from a starting node.

    Args:
        start_node: Node to start traversal from
        direction: Direction to traverse (upstream, downstream, or both)
        max_depth: Maximum traversal depth (-1 for unlimited)
        node_filter: Optional set of node types to include

    Yields:
        Tuples of (node_name, depth)
    """
    if not cmds.objExists(start_node):
        LOGGER.error("Start node does not exist: %s", start_node)
        return

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_node, 0)])

    while queue:
        current_node, depth = queue.popleft()

        if current_node in visited:
            continue
        if max_depth >= 0 and depth > max_depth:
            continue

        visited.add(current_node)

        if node_filter:
            node_type = cmds.nodeType(current_node)
            if node_type not in node_filter:
                continue

        yield current_node, depth

        next_nodes: list[str] = []

        if direction in (TraversalDirection.UPSTREAM, TraversalDirection.BOTH):
            upstream = cmds.listConnections(
                current_node, source=True, destination=False
            ) or []
            next_nodes.extend(upstream)

        if direction in (TraversalDirection.DOWNSTREAM, TraversalDirection.BOTH):
            downstream = cmds.listConnections(
                current_node, source=False, destination=True
            ) or []
            next_nodes.extend(downstream)

        for next_node in next_nodes:
            if next_node not in visited:
                queue.append((next_node, depth + 1))


def find_connected_nodes_by_type(
    start_node: str,
    target_type: str,
    direction: TraversalDirection = TraversalDirection.UPSTREAM,
) -> list[str]:
    """
    Find all connected nodes of a specific type.

    Args:
        start_node: Node to start search from
        target_type: Node type to find
        direction: Direction to search

    Returns:
        List of node names matching the target type
    """
    results: list[str] = []

    for node, _ in traverse_graph(start_node, direction):
        if cmds.nodeType(node) == target_type:
            results.append(node)

    return results


def get_shading_network(shader: str) -> dict[str, list[str]]:
    """
    Get the complete shading network for a shader node.

    Args:
        shader: Name of the shader node

    Returns:
        Dictionary mapping node types to lists of node names
    """
    network: dict[str, list[str]] = {}

    for node, _ in traverse_graph(shader, TraversalDirection.UPSTREAM, max_depth=20):
        node_type = cmds.nodeType(node)
        if node_type not in network:
            network[node_type] = []
        network[node_type].append(node)

    return network


class DGIterator:
    """
    OpenMaya-based dependency graph iterator for performance-critical operations.

    Uses the Maya API directly for faster traversal of large graphs.
    """

    def __init__(self, start_node: str) -> None:
        """
        Initialize the iterator.

        Args:
            start_node: Name of the starting node
        """
        selection_list = om.MSelectionList()
        selection_list.add(start_node)
        self._start_obj = selection_list.getDependNode(0)

    def get_upstream_nodes(
        self,
        traversal_type: int = om.MItDependencyGraph.kUpstream,
    ) -> list[str]:
        """
        Get all upstream nodes using the Maya API.

        Args:
            traversal_type: MItDependencyGraph traversal constant

        Returns:
            List of upstream node names
        """
        nodes: list[str] = []

        dg_iter = om.MItDependencyGraph(
            self._start_obj,
            om.MItDependencyGraph.kPlugLevel,
            traversal_type,
        )

        while not dg_iter.isDone():
            current_node = dg_iter.currentNode()
            node_fn = om.MFnDependencyNode(current_node)
            nodes.append(node_fn.name())
            dg_iter.next()

        return nodes

    def find_nodes_of_type(self, type_id: om.MTypeId) -> list[str]:
        """
        Find all connected nodes of a specific MTypeId.

        Args:
            type_id: Maya type ID to search for

        Returns:
            List of matching node names
        """
        nodes: list[str] = []

        dg_iter = om.MItDependencyGraph(
            self._start_obj,
            type_id,
            om.MItDependencyGraph.kPlugLevel,
            om.MItDependencyGraph.kUpstream,
        )

        while not dg_iter.isDone():
            current_node = dg_iter.currentNode()
            node_fn = om.MFnDependencyNode(current_node)
            nodes.append(node_fn.name())
            dg_iter.next()

        return nodes


def find_texture_nodes(shader: str) -> list[str]:
    """
    Find all texture file nodes connected to a shader.

    Args:
        shader: Name of the shader node

    Returns:
        List of file texture node names
    """
    return find_connected_nodes_by_type(shader, "file", TraversalDirection.UPSTREAM)


def get_mesh_shaders(mesh: str) -> list[str]:
    """
    Get all shaders assigned to a mesh.

    Args:
        mesh: Name of the mesh node

    Returns:
        List of shader node names
    """
    shapes = cmds.listRelatives(mesh, shapes=True, fullPath=True) or []
    shaders: list[str] = []

    for shape in shapes:
        shading_engines = cmds.listConnections(shape, type="shadingEngine") or []
        for sg in shading_engines:
            surface_shader = cmds.listConnections(f"{sg}.surfaceShader") or []
            shaders.extend(surface_shader)

    return list(set(shaders))


def print_node_tree(
    start_node: str,
    direction: TraversalDirection = TraversalDirection.UPSTREAM,
    max_depth: int = 5,
) -> None:
    """
    Print a visual tree representation of connected nodes.

    Args:
        start_node: Node to start from
        direction: Direction to traverse
        max_depth: Maximum depth to display
    """
    for node, depth in traverse_graph(start_node, direction, max_depth):
        indent = "  " * depth
        node_type = cmds.nodeType(node)
        print(f"{indent}├── {node} ({node_type})")
