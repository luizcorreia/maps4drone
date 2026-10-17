import io
import json

import pytest

from maps4drone import elevation


@pytest.fixture(autouse=True)
def clean_cache():
    elevation._cache.clear()
    yield
    elevation._cache.clear()


@pytest.fixture
def api(monkeypatch):
    calls: list[int] = []

    def fake_urlopen(url, timeout):
        query = dict(p.split("=") for p in url.split("?")[1].split("&"))
        lats = query["latitude"].replace("%2C", ",").split(",")
        calls.append(len(lats))
        return io.StringIO(json.dumps({"elevation": [100.0 + float(lat) for lat in lats]}))

    monkeypatch.setattr(elevation.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_values_follow_the_requested_points(api):
    lookup = elevation.open_meteo_elevation()
    assert lookup([(-51.9, 1.0), (-51.8, 2.0)]) == [101.0, 102.0]


def test_repeated_points_are_not_fetched_again(api):
    lookup = elevation.open_meteo_elevation()
    points = [(-51.9, 1.0), (-51.8, 2.0)]
    lookup(points)
    lookup(points)
    lookup([*points, (-51.7, 3.0)])
    assert api == [2, 1]


def test_nearby_points_share_a_cache_entry(api):
    lookup = elevation.open_meteo_elevation()
    lookup([(-51.9, 1.0)])
    lookup([(-51.900001, 1.000001)])
    assert api == [1]


def test_large_requests_are_split_into_batches(api):
    lookup = elevation.open_meteo_elevation()
    lookup([(-51.0, i * 0.01) for i in range(250)])
    assert api == [100, 100, 50]


def test_clearing_the_shared_cache_mid_call_does_not_lose_the_values(api, monkeypatch):
    """A full cache is wiped between chunks; the call still answers from what it gathered."""
    monkeypatch.setattr(elevation, "_CACHE_LIMIT", 50)
    monkeypatch.setattr(elevation, "_BATCH", 40)
    lookup = elevation.open_meteo_elevation()
    points = [(-51.0, i * 0.01) for i in range(120)]  # three chunks; the cache clears twice
    assert lookup(points) == [100.0 + i * 0.01 for i in range(120)]


def test_values_cached_by_an_earlier_call_survive_a_clear_during_this_one(api, monkeypatch):
    monkeypatch.setattr(elevation, "_CACHE_LIMIT", 10)
    lookup = elevation.open_meteo_elevation()
    first = [(-51.0, i * 0.01) for i in range(5)]
    lookup(first)
    more = first + [(-51.0, 1.0 + i * 0.01) for i in range(30)]
    assert lookup(more)[:5] == [100.0 + i * 0.01 for i in range(5)]
