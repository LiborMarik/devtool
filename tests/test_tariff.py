"""Testy pro výpočet koncové ceny podle tarifu."""

from datetime import datetime

import pytest

from ote.tariff import DISTRIBUTION_NT as DIST_NT
from ote.tariff import DISTRIBUTION_VT as DIST_VT
from ote.tariff import (
    compute_tariff_prices,
    czk_mwh_to_kwh,
    high_tariff_price,
    is_low_tariff,
    low_tariff_price,
    price_level,
    sell_price_kwh,
    total_price_kwh,
)


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(0, False), (3, False), (4, True), (7, True), (8, False), (14, False), (15, True),
     (18, True), (19, False), (23, False)],
)
def test_is_low_tariff(hour: int, expected: bool) -> None:
    assert is_low_tariff(hour) is expected


def test_is_low_tariff_minutes_and_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    import ote.tariff as tariff

    monkeypatch.setattr(tariff, "LOW_TARIFF_PERIODS", (("22:30", "02:15"), ("12:00", "13:00")))
    assert tariff.is_low_tariff(22, 15) is False
    assert tariff.is_low_tariff(22, 30) is True
    assert tariff.is_low_tariff(1, 0) is True
    assert tariff.is_low_tariff(2, 15) is False
    assert tariff.is_low_tariff(12, 45) is True


def test_total_price_matches_my_price_list() -> None:
    # Spot 2,00 Kč/kWh: 2 × 1,21 + pevná část z ceníku (VT 2,15317 / NT 0,92666)
    assert low_tariff_price(2.0) == pytest.approx(2.42 + 0.92666, abs=1e-4)
    assert high_tariff_price(2.0) == pytest.approx(2.42 + 2.15317, abs=1e-4)


def test_components_add_up_to_fixed_part() -> None:
    from ote.tariff import ELECTREE_FEE, ENERGY_TAX, FIXED_NT, FIXED_VT, SYSTEM_SERVICES

    rest = ELECTREE_FEE + SYSTEM_SERVICES + ENERGY_TAX
    assert DIST_VT + rest == pytest.approx(FIXED_VT, abs=1e-5)
    assert DIST_NT + rest == pytest.approx(FIXED_NT, abs=1e-5)


def test_negative_spot() -> None:
    assert total_price_kwh(-0.5, low_tariff=True) == pytest.approx(-0.605 + 0.92666)


def test_compute_tariff_prices() -> None:
    rows = compute_tariff_prices([
        (datetime(2026, 10, 20, 5, 0), 1500.0),
        (datetime(2026, 10, 20, 12, 15), 1500.0),
    ])
    assert czk_mwh_to_kwh(1500.0) == 1.5
    assert rows[0].is_low_tariff and not rows[1].is_low_tariff
    assert rows[0].spot_kwh == 1.5
    assert rows[1].total_kwh - rows[0].total_kwh == pytest.approx(DIST_VT - DIST_NT)


@pytest.mark.parametrize(
    ("current", "references", "expected"),
    [
        (7.0, [7.0, 7.2], "normální"),
        (8.5, [7.0, 7.2], "vysoká"),
        (5.5, [7.0, 7.2], "nízká"),
        (7.0, [7.0], "normální"),
        (7.0, [], None),
    ],
)
def test_price_level(current: float, references: list[float], expected: str | None) -> None:
    assert price_level(current, references) == expected


def test_sell_price() -> None:
    # Výkup bez poplatku = spot bez DPH
    assert sell_price_kwh(2.0) == pytest.approx(2.0)
    # Při záporném spotu se za dodávku do sítě platí
    assert sell_price_kwh(-0.1) == pytest.approx(-0.1)
