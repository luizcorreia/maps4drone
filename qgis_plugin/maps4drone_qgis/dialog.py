from qgis.PyQt.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

SAFETY = (
    "This plugin generates plans that command a real drone. Test in a small open area with "
    "line of sight and follow your local aviation rules (Brazil: ANAC/DECEA, 120 m AGL).\n\n"
    "The camera shooting interval is NOT stored in the Atom 2 mission file: set the same "
    "interval in the app's camera timer before flying."
)

ENTRIES = [
    ("maps4drone:survey_grid", "Survey grid / double grid"),
    ("maps4drone:corridor", "Corridor"),
    ("maps4drone:orbit", "Orbit"),
    ("maps4drone:facade", "Facade (experimental)"),
]


class LauncherDialog(QDialog):
    """Small launcher that opens the Processing dialog of each algorithm."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("maps4drone")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Plan a mission with:"))
        for algorithm_id, label in ENTRIES:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, a=algorithm_id: self._open(a))
            layout.addWidget(button)
        notice = QLabel(SAFETY)
        notice.setWordWrap(True)
        layout.addWidget(notice)

    def _open(self, algorithm_id: str) -> None:
        import processing

        self.close()
        processing.execAlgorithmDialog(algorithm_id)
