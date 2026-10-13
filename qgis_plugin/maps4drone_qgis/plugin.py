from pathlib import Path

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox

try:
    from qgis.PyQt.QtGui import QAction  # Qt6 / QGIS 4
except ImportError:
    from qgis.PyQt.QtWidgets import QAction  # Qt5 / QGIS 3

from ._deps import ensure_core

MENU = "&maps4drone"


class Maps4DronePlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.provider = None
        self.action = None
        self.problem = None

    def initGui(self) -> None:  # noqa: N802
        self.problem = ensure_core()
        icon = QIcon(str(Path(__file__).parent / "icon.svg"))
        self.action = QAction(icon, "maps4drone", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(MENU, self.action)
        self.iface.addToolBarIcon(self.action)
        if self.problem is None:
            from .provider import Maps4DroneProvider

            self.provider = Maps4DroneProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)
        else:
            self.iface.messageBar().pushWarning(
                "maps4drone", "Missing dependencies. Click the maps4drone button for details."
            )

    def unload(self) -> None:
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
        if self.action is not None:
            self.iface.removePluginMenu(MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self) -> None:
        if self.problem is not None:
            QMessageBox.critical(self.iface.mainWindow(), "maps4drone cannot start", self.problem)
            return
        from .dialog import LauncherDialog

        LauncherDialog(self.iface.mainWindow()).exec()
