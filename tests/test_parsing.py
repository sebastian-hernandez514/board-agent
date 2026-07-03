import pytest

from board_agent.parsing import find_row, parse_cell, parse_money_cell


@pytest.mark.parametrize("raw,expected", [
    ("$29.2M", 29_200_000.0),
    ("$611K", 611_000.0),
    ("(0.9)", -0.9),
    ("5.2%", 5.2),
    ("26.5", 26.5),
    ("23.4k", 23_400.0),
    ("3,714", 3714.0),
    (4.1, 4.1),  # ya viene como float en metrics.yaml (logo_churn_global)
])
def test_parse_cell(raw, expected):
    assert parse_cell(raw) == pytest.approx(expected)


def test_parse_cell_empty_raises():
    with pytest.raises(ValueError):
        parse_cell("—")


@pytest.mark.parametrize("raw,expected", [
    ("26.5", 26_500_000.0),   # ARR Walk: bare number = $M
    ("(0.9)", -900_000.0),
    ("$611K", 611_000.0),      # con sufijo explícito no se reescala
])
def test_parse_money_cell(raw, expected):
    assert parse_money_cell(raw) == pytest.approx(expected)


def test_find_row():
    rows = [{"label": "Additions", "cells": ["0.8", "0.9"]}, {"label": "Recovered", "cells": ["0.2", "0.2"]}]
    assert find_row(rows, "Recovered") == ["0.2", "0.2"]


def test_find_row_missing_raises_with_available_labels():
    rows = [{"label": "Additions", "cells": []}]
    with pytest.raises(KeyError, match="Additions"):
        find_row(rows, "Nope")
