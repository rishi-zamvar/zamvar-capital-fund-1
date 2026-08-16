"""The shared seed-CSV reader: blank lines + '#'-comment lines are skipped, rows come back as dicts."""

from catalyst_trader.csvrows import read_csv_rows


def test_read_csv_rows_skips_blanks_and_comments(tmp_path):
    p = tmp_path / "seed.csv"
    p.write_text(
        "# template header comment\n"
        "ticker,company_name,delisted\n"
        "\n"
        "  # indented comment line\n"
        "VRTX,Vertex,false\n"
        "\n"
        "SRPT,Sarepta,true\n"
    )
    rows = read_csv_rows(p)
    assert rows == [
        {"ticker": "VRTX", "company_name": "Vertex", "delisted": "false"},
        {"ticker": "SRPT", "company_name": "Sarepta", "delisted": "true"},
    ]


def test_read_csv_rows_empty_file_is_empty(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("# only a comment\n\n")
    assert read_csv_rows(p) == []
