"""Tests for scripts/setup_data.py's CSV parsing and the manual-CSV fallback
path (a user can drop mids.csv/wars.csv/capabilities.csv directly into
data/cow/ — e.g. downloaded by hand in a browser when the script's own
download fails, which happens on some networks due to correlatesofwar.org
not serving its full certificate chain). Loader tests pin down the exact
column layouts of real CoW downloads (verified against actual files: MIDA
5.0, NMC-70-abridged, Intra-State Wars v5.1) so a future CoW format change
surfaces as a test failure instead of a silent zero-rows-loaded run.
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


def test_load_mids_parses_real_mida_5_0_format():
    """MIDA 5.0 is dispute-level (one row per dispute) — no state columns at
    all, unlike the dyadic MIDB file. Header/row taken from an actual
    MIDA_5.0.csv download."""
    conn = _conn_with_tables()
    csv_text = (
        "dispnum,stday,stmon,styear,endday,endmon,endyear,outcome,settle,fatality,"
        "fatalpre,maxdur,mindur,hiact,hostlev,recip,numa,numb,ongo2014,version\n"
        "2,-9,7,1902,24,1,1903,6,1,0,0,208,178,7,3,0,1,1,0,5\n"
    )
    n = setup_data.load_mids(conn, csv_text)
    assert n == 1
    row = conn.execute(
        "SELECT dispute_number, side_a_state, start_year, end_year, hostility_level, outcome FROM cow_mids"
    ).fetchone()
    assert row == (2, "", 1902, 1903, 3, 6)


def test_load_mids_treats_negative_sentinels_as_missing():
    """CoW uses negative codes (-7/-8/-9) for missing/inapplicable data across
    every dataset; endyear=-9 here means "ongoing" and must become NULL, not
    the literal value -9."""
    conn = _conn_with_tables()
    csv_text = "dispnum,styear,endyear,hostlev,outcome\n5,2010,-9,4,-9\n"
    n = setup_data.load_mids(conn, csv_text)
    assert n == 1
    row = conn.execute("SELECT end_year, outcome FROM cow_mids").fetchone()
    assert row == (None, None)


def test_load_mids_skips_malformed_rows():
    conn = _conn_with_tables()
    csv_text = "dispnum,styear,endyear,hostlev,outcome\nnot-a-number,1990,1991,5,1\n"
    n = setup_data.load_mids(conn, csv_text)
    assert n == 0


def test_load_mids_still_picks_up_state_column_when_present():
    """Some MID file variants (e.g. dyadic MIDB) do carry a StateAbb column —
    if present, use it."""
    conn = _conn_with_tables()
    csv_text = "DispNum3,StateAbb,StYear,EndYear,HostLev,Outcome\n1,USA,1990,1991,5,1\n"
    n = setup_data.load_mids(conn, csv_text)
    assert n == 1
    row = conn.execute("SELECT side_a_state FROM cow_mids").fetchone()
    assert row == ("USA",)


def test_load_wars_parses_real_intra_state_v5_1_format():
    """Header/row taken from an actual INTRA-STATE_WARS_v5.1_CSV.csv download —
    note StartYr1/EndYr1, not StartYear1/EndYear1 (that's the v4.0 Inter-State
    spelling, also supported)."""
    conn = _conn_with_tables()
    csv_text = (
        "WarNum,WarName,V5RegionNum,WarType,CcodeA,SideA,SideB,Intnl,StartMo1,StartDy1,StartYr1,"
        "EndMo1,EndDy1,EndYr1,WDuratDays,WDuratMo,TotNatMonWar,TransFrom,Initiator,Outcome,TransTo,"
        "DeathsSideA,DeathsSideB,TotalBDeaths,Version\n"
        "500,First Caucasus War of 1818-1822,3,5,365,Russia,Caucasus Rebels,0,6,10,1818,11,-9,1822,"
        "1596,53.2,53.2,-8,Chechnya,1,-8,5000,6000,11000,5.1\n"
    )
    n = setup_data.load_wars(conn, csv_text)
    assert n == 1
    row = conn.execute(
        "SELECT war_number, war_name, start_year, end_year, outcome, duration_days FROM cow_wars"
    ).fetchone()
    assert row == (500, "First Caucasus War of 1818-1822", 1818, 1822, 1, 1596)


def test_load_wars_accepts_inter_state_v4_0_column_spelling():
    conn = _conn_with_tables()
    csv_text = "WarNum,WarName,StartYear1,EndYear1,Outcome\n100,Test War,1990,1991,1\n"
    n = setup_data.load_wars(conn, csv_text)
    assert n == 1
    row = conn.execute("SELECT war_number, war_name, start_year, end_year, outcome FROM cow_wars").fetchone()
    assert row == (100, "Test War", 1990, 1991, 1)


def test_load_capabilities_parses_real_nmc_70_abridged_format():
    """Header/row taken from an actual NMC-70-abridged.csv download — note
    there is no full-name column at all in the abridged file, only
    `stateabb`."""
    conn = _conn_with_tables()
    csv_text = "stateabb,ccode,year,milex,milper,irst,pec,tpop,upop,cinc,version\nUSA,2,1816,3823,17,80,254,8659,101,.039697491,2025\n"
    n = setup_data.load_capabilities(conn, csv_text)
    assert n == 1
    row = conn.execute("SELECT state_name, year, cinc FROM cow_capabilities").fetchone()
    assert row == ("USA", 1816, 0.039697491)


def test_load_capabilities_falls_back_to_full_name_column():
    conn = _conn_with_tables()
    csv_text = "StateNme,Year,CINC\nUnited States of America,1990,0.15\n"
    n = setup_data.load_capabilities(conn, csv_text)
    assert n == 1
    row = conn.execute("SELECT state_name, year, cinc FROM cow_capabilities").fetchone()
    assert row == ("United States of America", 1990, 0.15)


def test_main_loads_manually_placed_csvs_without_network(tmp_path, monkeypatch):
    cow_dir = tmp_path / "cow"
    cow_dir.mkdir()
    (cow_dir / "mids.csv").write_text("dispnum,styear,endyear,hostlev,outcome\n1,1990,1991,5,1\n")
    (cow_dir / "wars.csv").write_text("WarNum,WarName,StartYr1,EndYr1,Outcome\n100,Test War,1990,1991,1\n")
    (cow_dir / "capabilities.csv").write_text("stateabb,year,cinc\nUSA,1990,0.15\n")

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
