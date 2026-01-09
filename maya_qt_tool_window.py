"""
Maya Qt Tool Window

A reusable Qt window template for Maya tools demonstrating proper
widget lifecycle, signal management, and Maya integration patterns.
"""
from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from Qt import QtCore, QtGui, QtWidgets
from Qt.QtCore import Signal

from maya import cmds

if TYPE_CHECKING:
    from collections.abc import Callable

from crafty_logger import get_logger

LOGGER = get_logger("qt_tool_window")

WINDOW_TITLE = "Asset Browser"
WINDOW_OBJECT_NAME = "assetBrowserWindow"


def get_maya_main_window() -> QtWidgets.QWidget | None:
    """Get the Maya main window as a Qt widget."""
    try:
        from maya import OpenMayaUI
        from shiboken2 import wrapInstance

        main_window_ptr = OpenMayaUI.MQtUtil.mainWindow()
        return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)
    except ImportError:
        LOGGER.warning("Could not import shiboken2, running outside Maya")
        return None


def delete_existing_window(object_name: str) -> None:
    """Delete any existing window with the given object name."""
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == object_name:
            widget.close()
            widget.deleteLater()


class AssetItem:
    """Represents an asset in the browser."""

    def __init__(
        self,
        name: str,
        path: str,
        asset_type: str,
        thumbnail: str | None = None,
    ) -> None:
        self.name = name
        self.path = path
        self.asset_type = asset_type
        self.thumbnail = thumbnail


class AssetListModel(QtCore.QAbstractListModel):
    """Custom model for displaying assets in a list view."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._assets: list[AssetItem] = []

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._assets)

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.DisplayRole,
    ) -> str | None:
        if not index.isValid() or not 0 <= index.row() < len(self._assets):
            return None

        asset = self._assets[index.row()]

        if role == QtCore.Qt.DisplayRole:
            return asset.name
        if role == QtCore.Qt.ToolTipRole:
            return f"{asset.asset_type}: {asset.path}"
        if role == QtCore.Qt.UserRole:
            return asset

        return None

    def set_assets(self, assets: list[AssetItem]) -> None:
        """Replace the current asset list."""
        self.beginResetModel()
        self._assets = assets
        self.endResetModel()

    def get_asset(self, index: QtCore.QModelIndex) -> AssetItem | None:
        """Get an asset by model index."""
        if index.isValid() and 0 <= index.row() < len(self._assets):
            return self._assets[index.row()]
        return None


class FilterProxyModel(QtCore.QSortFilterProxyModel):
    """Proxy model for filtering and sorting assets."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._type_filter: str = ""
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

    def set_type_filter(self, asset_type: str) -> None:
        """Filter by asset type."""
        self._type_filter = asset_type
        self.invalidateFilter()

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QtCore.QModelIndex,
    ) -> bool:
        source_model = self.sourceModel()
        index = source_model.index(source_row, 0, source_parent)
        asset = source_model.data(index, QtCore.Qt.UserRole)

        if not asset:
            return False

        if self._type_filter and asset.asset_type != self._type_filter:
            return False

        filter_text = self.filterRegExp().pattern()
        if filter_text and filter_text.lower() not in asset.name.lower():
            return False

        return True


class AssetBrowserWidget(QtWidgets.QWidget):
    """Main widget for browsing and importing assets."""

    asset_selected = Signal(object)
    asset_imported = Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = AssetListModel(self)
        self._proxy_model = FilterProxyModel(self)
        self._proxy_model.setSourceModel(self._model)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Build the widget UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        filter_layout = QtWidgets.QHBoxLayout()

        self._search_edit = QtWidgets.QLineEdit()
        self._search_edit.setPlaceholderText("Search assets...")
        self._search_edit.setClearButtonEnabled(True)
        filter_layout.addWidget(self._search_edit)

        self._type_combo = QtWidgets.QComboBox()
        self._type_combo.addItems(["All Types", "Model", "Rig", "Animation", "Texture"])
        self._type_combo.setMinimumWidth(120)
        filter_layout.addWidget(self._type_combo)

        layout.addLayout(filter_layout)

        self._list_view = QtWidgets.QListView()
        self._list_view.setModel(self._proxy_model)
        self._list_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self._list_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        layout.addWidget(self._list_view)

        button_layout = QtWidgets.QHBoxLayout()

        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        button_layout.addWidget(self._refresh_btn)

        button_layout.addStretch()

        self._reference_btn = QtWidgets.QPushButton("Reference")
        button_layout.addWidget(self._reference_btn)

        self._import_btn = QtWidgets.QPushButton("Import")
        button_layout.addWidget(self._import_btn)

        layout.addLayout(button_layout)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._type_combo.currentTextChanged.connect(self._on_type_filter_changed)
        self._list_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._list_view.doubleClicked.connect(self._on_item_double_clicked)
        self._list_view.customContextMenuRequested.connect(self._show_context_menu)
        self._refresh_btn.clicked.connect(self.refresh_assets)
        self._reference_btn.clicked.connect(self._reference_selected)
        self._import_btn.clicked.connect(self._import_selected)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text changes."""
        self._proxy_model.setFilterRegExp(text)

    def _on_type_filter_changed(self, type_text: str) -> None:
        """Handle asset type filter changes."""
        filter_type = "" if type_text == "All Types" else type_text
        self._proxy_model.set_type_filter(filter_type)

    def _on_selection_changed(self) -> None:
        """Handle selection changes in the list view."""
        indexes = self._list_view.selectionModel().selectedIndexes()
        if indexes:
            source_index = self._proxy_model.mapToSource(indexes[0])
            asset = self._model.get_asset(source_index)
            if asset:
                self.asset_selected.emit(asset)

    def _on_item_double_clicked(self, index: QtCore.QModelIndex) -> None:
        """Handle double-click to import asset."""
        source_index = self._proxy_model.mapToSource(index)
        asset = self._model.get_asset(source_index)
        if asset:
            self._import_asset(asset, as_reference=True)

    def _show_context_menu(self, position: QtCore.QPoint) -> None:
        """Show context menu for selected assets."""
        menu = QtWidgets.QMenu(self)

        reference_action = menu.addAction("Reference")
        import_action = menu.addAction("Import")
        menu.addSeparator()
        open_folder_action = menu.addAction("Open Containing Folder")

        action = menu.exec_(self._list_view.mapToGlobal(position))

        if action == reference_action:
            self._reference_selected()
        elif action == import_action:
            self._import_selected()
        elif action == open_folder_action:
            self._open_asset_folder()

    def _reference_selected(self) -> None:
        """Reference selected assets into the scene."""
        for asset in self._get_selected_assets():
            self._import_asset(asset, as_reference=True)

    def _import_selected(self) -> None:
        """Import selected assets into the scene."""
        for asset in self._get_selected_assets():
            self._import_asset(asset, as_reference=False)

    def _get_selected_assets(self) -> list[AssetItem]:
        """Get all selected assets."""
        assets = []
        for index in self._list_view.selectionModel().selectedIndexes():
            source_index = self._proxy_model.mapToSource(index)
            asset = self._model.get_asset(source_index)
            if asset:
                assets.append(asset)
        return assets

    def _import_asset(self, asset: AssetItem, as_reference: bool = True) -> None:
        """Import or reference an asset into Maya."""
        try:
            if as_reference:
                namespace = asset.name.replace(" ", "_")
                cmds.file(
                    asset.path,
                    reference=True,
                    namespace=namespace,
                    mergeNamespacesOnClash=True,
                )
                LOGGER.info("Referenced asset: %s", asset.name)
            else:
                cmds.file(asset.path, i=True, mergeNamespacesOnClash=True)
                LOGGER.info("Imported asset: %s", asset.name)

            self.asset_imported.emit(asset.path)
        except RuntimeError as e:
            LOGGER.exception(e)
            QtWidgets.QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import {asset.name}:\n{e}",
            )

    def _open_asset_folder(self) -> None:
        """Open the folder containing the selected asset."""
        assets = self._get_selected_assets()
        if assets:
            import os
            import subprocess

            folder = os.path.dirname(assets[0].path)
            if os.path.exists(folder):
                subprocess.Popen(["explorer", folder])

    def refresh_assets(self) -> None:
        """Refresh the asset list from the database/filesystem."""
        sample_assets = [
            AssetItem("Character_Hero", "/assets/characters/hero.ma", "Rig"),
            AssetItem("Prop_Sword", "/assets/props/sword.ma", "Model"),
            AssetItem("Env_Forest", "/assets/environments/forest.ma", "Model"),
            AssetItem("Anim_Walk", "/assets/animations/walk.ma", "Animation"),
        ]
        self._model.set_assets(sample_assets)

    def set_assets(self, assets: list[AssetItem]) -> None:
        """Set the asset list."""
        self._model.set_assets(assets)


class AssetBrowserWindow(QtWidgets.QMainWindow):
    """Main window for the Asset Browser tool."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(WINDOW_TITLE)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self._browser_widget = AssetBrowserWidget(self)
        self.setCentralWidget(self._browser_widget)

        self._setup_menubar()
        self._setup_statusbar()
        self._connect_signals()
        self._restore_geometry()

        self._browser_widget.refresh_assets()

    def _setup_menubar(self) -> None:
        """Create the menu bar."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("Refresh", self._browser_widget.refresh_assets, "F5")
        file_menu.addSeparator()
        file_menu.addAction("Close", self.close, "Ctrl+W")

        view_menu = menubar.addMenu("View")
        view_menu.addAction("Reset Window", self._reset_geometry)

    def _setup_statusbar(self) -> None:
        """Create the status bar."""
        self.statusBar().showMessage("Ready")

    def _connect_signals(self) -> None:
        """Connect signals from child widgets."""
        self._browser_widget.asset_selected.connect(self._on_asset_selected)
        self._browser_widget.asset_imported.connect(self._on_asset_imported)

    def _on_asset_selected(self, asset: AssetItem) -> None:
        """Handle asset selection."""
        self.statusBar().showMessage(f"Selected: {asset.name}")

    def _on_asset_imported(self, path: str) -> None:
        """Handle asset import."""
        self.statusBar().showMessage(f"Imported: {path}")

    def _save_geometry(self) -> None:
        """Save window geometry to Maya preferences."""
        geometry = self.saveGeometry().toBase64().data().decode()
        cmds.optionVar(stringValue=(f"{WINDOW_OBJECT_NAME}_geometry", geometry))

    def _restore_geometry(self) -> None:
        """Restore window geometry from Maya preferences."""
        if cmds.optionVar(exists=f"{WINDOW_OBJECT_NAME}_geometry"):
            geometry = cmds.optionVar(query=f"{WINDOW_OBJECT_NAME}_geometry")
            self.restoreGeometry(QtCore.QByteArray.fromBase64(geometry.encode()))
        else:
            self.resize(400, 600)

    def _reset_geometry(self) -> None:
        """Reset window to default size and position."""
        self.resize(400, 600)
        self.move(100, 100)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Handle window close event."""
        self._save_geometry()
        super().closeEvent(event)


def show() -> AssetBrowserWindow:
    """Show the Asset Browser window."""
    delete_existing_window(WINDOW_OBJECT_NAME)

    parent = get_maya_main_window()
    window = AssetBrowserWindow(parent)
    window.show()
    window.raise_()

    return window
