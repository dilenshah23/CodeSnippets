# Maya & VFX Pipeline Code Snippets

A collection of production-ready Python code snippets demonstrating Maya API, USD, Qt, and VFX pipeline patterns.

## Contents

### Maya API

| File | Description |
|------|-------------|
| `maya_api_deformer.py` | OpenMaya 2.0 custom deformer plugin with wave and noise deformers |
| `maya_node_graph.py` | Dependency graph traversal utilities using both cmds and OpenMaya |
| `maya_scene_exporter.py` | Production scene exporter with validation workflows |
| `maya_selection_utils.py` | Advanced selection utilities with filtering and history |
| `maya_qt_tool_window.py` | Qt-based tool window template with proper Maya integration |
| `AETemplates_Example` | Maya Attribute Editor template guide |

### USD

| File | Description |
|------|-------------|
| `usd_composition_utils.py` | USD layer management, composition arcs, and scene assembly |

## Key Features Demonstrated

- **Maya Python API 2.0**: Custom deformer nodes with proper plugin registration
- **Dependency Graph**: BFS traversal, node filtering, shading network analysis
- **Qt/PySide**: Model-View architecture, signal management, window persistence
- **USD**: Composition arcs, variants, layer management, stage metadata
- **Production Patterns**: Dataclasses, type hints, validation, logging

## Usage

These snippets are designed as reference implementations. Import and adapt them for your pipeline:

```python
from maya_selection_utils import select_hierarchy, SelectionFilter

# Select all meshes in hierarchy
filter_config = SelectionFilter(node_types=["mesh"], visible_only=True)
select_hierarchy(filter_config=filter_config)
```

## Requirements

- Maya 2022+ (Python 3.9+)
- USD 21.11+
- Qt.py (or PySide2/PySide6)

## Author

Dilen Shah
