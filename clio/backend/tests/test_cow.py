import sqlite3

import pytest

from app.sources.cow import CoWDataClient, CoWDataUnavailableError


@pytest.fixture
def cow_db(tmp_path):
    db_path = tmp_path / "clio_test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE cow_mids (
            dispute_number INTEGER, side_a_state TEXT, side_b_state TEXT,
            start_year INTEGER, end_year INTEGER, hostility_level INTEGER, outcome INTEGER
        );
        CREATE TABLE cow_wars (
            war_number INTEGER, war_name TEXT, start_year INTEGER,
            end_year INTEGER, outcome INTEGER, duration_days INTEGER
        );
        CREATE TABLE cow_capabilities (state_name TEXT, year INTEGER, cinc REAL);
        """
    )
    conn.executemany(
        "INSERT INTO cow_mids VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "USA", "", 1990, 1991, 5, 1),
            (2, "GBR", "", 1985, 1985, 2, 3),
            (3, "FRA", "", 1970, 1970, 5, 2),
        ],
    )
    conn.executemany(
        "INSERT INTO cow_wars VALUES (?, ?, ?, ?, ?, ?)",
        [(100, "Test War", 1990, 1991, 1, 200)],
    )
    conn.executemany(
        "INSERT INTO cow_capabilities VALUES (?, ?, ?)",
        [("USA", 1990, 0.15), ("Iraq", 1990, 0.01)],
    )
    conn.commit()
    conn.close()
    return db_path


def test_is_available_true_when_tables_present(cow_db):
    client = CoWDataClient(sqlite_path=cow_db)
    assert client.is_available() is True


def test_is_available_false_when_missing(tmp_path):
    client = CoWDataClient(sqlite_path=tmp_path / "nope.db")
    assert client.is_available() is False


def test_query_mids_filters_by_hostility(cow_db):
    client = CoWDataClient(sqlite_path=cow_db)
    wars_level = client.query_mids(min_hostility=5, max_hostility=5)
    assert len(wars_level) == 2
    assert {m.dispute_number for m in wars_level} == {1, 3}


def test_query_wars(cow_db):
    client = CoWDataClient(sqlite_path=cow_db)
    wars = client.query_wars()
    assert len(wars) == 1
    assert wars[0].war_name == "Test War"


def test_cinc_ratio(cow_db):
    client = CoWDataClient(sqlite_path=cow_db)
    ratio = client.cinc_ratio("USA", "Iraq", 1990)
    assert ratio == pytest.approx(15.0)


def test_cinc_ratio_none_when_missing(cow_db):
    client = CoWDataClient(sqlite_path=cow_db)
    assert client.cinc_ratio("USA", "Atlantis", 1990) is None


def test_raises_when_db_missing(tmp_path):
    client = CoWDataClient(sqlite_path=tmp_path / "missing.db")
    with pytest.raises(CoWDataUnavailableError):
        client.query_wars()
