from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms import ALGORITHMS


class Maps4DroneProvider(QgsProcessingProvider):
    def id(self) -> str:
        return "maps4drone"

    def name(self) -> str:
        return "maps4drone"

    def longName(self) -> str:  # noqa: N802
        return "maps4drone - drone mapping missions"

    def icon(self) -> QIcon:
        return QIcon(str(Path(__file__).parent / "icon.svg"))

    def loadAlgorithms(self) -> None:  # noqa: N802
        for algorithm in ALGORITHMS:
            self.addAlgorithm(algorithm())
