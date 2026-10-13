import pytest
from shapely.geometry import Polygon

from maps4drone.camera import Drone, load_drones


@pytest.fixture(scope="session")
def atom2() -> Drone:
    return load_drones()["atom2"]


@pytest.fixture
def square() -> Polygon:
    """Roughly 400 m x 300 m near Itauna, MG."""
    return Polygon(
        [(-51.9000, -23.1500), (-51.8964, -23.1500), (-51.8964, -23.1473), (-51.9000, -23.1473)]
    )
