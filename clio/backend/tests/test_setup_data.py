"""Tests for scripts/setup_data.py's CSV parsing and the manual-CSV fallback
path (a user can drop mids.csv/wars.csv/capabilities.csv directly into
data/cow/ — e.g. downloaded by hand in a browser when the script's own
download fails, which happens on some networks due to correlatesofwar.org
not serving its full certificate chain). Loader tests pin down the expected
column names so a future CoW format change surfaces as a test failure
instead of a silent zero-rows-loaded run.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import setup_data  # noqa: E402


def _conn_with_tables():
    conn = sqlite3.connect(":memory:")
    setup_data.create_tables(conn)
    return conn


def test_load_mids_parses_standard_columns():
    conn = _conn_with_tables()
    csv_text = (
        "DispNum3,StateAbb,StYear,EndYear,HostLev,Outcome\n"
        "1,USA,1990,1991,5,1\n"
        "2,GBR,1985,1985,2,3\n"
    )
    n = setup_data.load_mids(conn, csv_text)
    assert n == 2
    rows = conn.execute("SELECT dispute_number, side_a_state, start_year, hostility_level, outcome FROM cow_mids").fetchall()
    assert rows == [(1, "USA", 1990, 5, 1), (2, "GBR", 1985, 2, 3)]


def test_load_mids_skips_malformed_rows():
    conn = _conn_with_tables()
    csv_text = "DispNum3,StateAbb,StYear,EndYear,HostLev,Outcome\nnot-a-number,USA,1990,1991,5,1\n"
    n = setup_data.load_mids(conn, csv_text)
    assert n == 0


def test_load_wars_parses_standard_columns():
    conn = _conn_with_tables()
    csv_text = "WarNum,WarName,StartYear1,EndYear1,Outcome\n100,Test War,1990,1991,1\n"
    n = setup_data.load_wars(conn, csv_text)
    assert n == 1
    row = conn.execute("SELECT war_number, war_name, start_year, end_year, outcome FROM cow_wars").fetchone()
    assert row == (100, "Test War", 1990, 1991, 1)


def test_load_capabilities_parses_standard_columns():
    conn = _conn_with_tables()
    csv_text = "StateNme,Year,CINC\nUnited States of America,1990,0.15\n"
    n = setup_data.load_capabilities(conn, csv_text)
    assert n == 1
    row = conn.execute("SELECT state_name, year, cinc FROM cow_capabilities").fetchone()
    assert row == ("United States of America", 1990, 0.15)


def test_main_loads_manually_placed_csvs_without_network(tmp_path, monkeypatch):
    cow_dir = tmp_path / "cow"
    cow_dir.mkdir()
    (cow_dir / "mids.csv").write_text("DispNum3,StateAbb,StYear,EndYear,HostLev,Outcome\n1,USA,1990,1991,5,1\n")
    (cow_dir / "wars.csv").write_text("WarNum,WarName,StartYear1,EndYear1,Outcome\n100,Test War,1990,1991,1\n")
    (cow_dir / "capabilities.csv").write_text("StateNme,Year,CINC\nUSA,1990,0.15\n")

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "clio.db"))
    monkeypatch.setenv("COW_DATA_DIR", str(cow_dir))
    setup_data.get_settings.cache_clear()

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("download_zip should not be called when manual CSVs are present")

    monkeypatch.setattr(setup_data, "download_zip", _fail_if_called)

    exit_code = setup_data.main()

    setup_data.get_settings.cache_clear()
    assert exit_code == 0

    conn = sqlite3.connect(tmp_path / "clio.db")
    assert conn.execute("SELECT COUNT(*) FROM cow_mids").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM cow_wars").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM cow_capabilities").fetchone()[0] == 1
