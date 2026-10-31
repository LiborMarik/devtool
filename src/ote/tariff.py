"""Výpočet koncové ceny elektřiny podle mého tarifu.

Distribuce EG.D, sazba D26d, ceny 2026 bez POZE. Všechno, co se liší podle odběrného
místa (dodavatel, poplatky, časy nízkého tarifu, místo pro počasí), je v sekci NASTAVENÍ.
Ceny poplatků jsou v Kč/kWh s DPH, spot se přepočítává z CZK/MWh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# ═══ NASTAVENÍ – tady se upravuje vše pro konkrétní odběrné místo ═══════════════

LOCATION_NAME = "Mirovice"
LOCATION_COORDS = {"latitude": 49.516, "longitude": 14.034}  # Mirovice, okres Písek

SUPPLIER = "dodavatele"  # ve 2. pádě – tak se zobrazuje v textech („poplatek dodavatele")
DISTRIBUTOR = "EG.D D26d"

# Pevná část ceny za odběr (vše kromě spotu), Kč/kWh s DPH – údaj z mého ceníku.
# Obsahuje distribuci, systémové služby, daň i poplatek dodavatele.
FIXED_VT = 2.15317
FIXED_NT = 0.92666

# Stálý měsíční plat dodavateli, Kč (nezávisí na spotřebě ani jističi)
MONTHLY_FEE = 180.0

# Distribuce EG.D, sazba D26d, ceník 2026, Kč/kWh s DPH
DISTRIBUTION_VT = 1.49791  # 1 237,94 Kč/MWh bez DPH
DISTRIBUTION_NT = 0.27140  # 224,30 Kč/MWh bez DPH
SYSTEM_SERVICES = 0.19873  # 164,24 Kč/MWh bez DPH (stejné v celé ČR)
ENERGY_TAX = 0.03424  # 28,30 Kč/MWh bez DPH

# Poplatek dodavatele za odběr = zbytek pevné části po distribuci, službách a dani.
# Ve VT i NT vychází stejně (0,42229 Kč/kWh), takže rozpad ceny sedí s ceníkem.
ELECTREE_FEE = round(FIXED_VT - DISTRIBUTION_VT - SYSTEM_SERVICES - ENERGY_TAX, 5)

# DPH se přičítá ke spotové ceně (poplatky výše už DPH obsahují)
VAT = 1.21

# Výkup (prodej přetoků do sítě): spot bez DPH minus poplatek dodavatele, Kč/kWh.
# Za výkup se žádný poplatek neplatí.
SELL_FEE = 0.0

# Nízký tarif (HDO) – úseky „od–do" v místním čase, konec se nezapočítává.
# D26d má 8 h NT denně, přesné časy určuje kód HDO (egd.cz → Časy spínání HDO).
# Moje HDO: 4–8 a 15–19 h, každý den včetně víkendu.
LOW_TARIFF_PERIODS = (("04:00", "08:00"), ("15:00", "19:00"))

# ══════════════════════════════════════════════════════════════════════════════


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


@dataclass
class TariffPrice:
    """Koncová cena pro jeden interval."""

    time_from: datetime
    spot_kwh: float
    is_low_tariff: bool
    total_kwh: float


def is_low_tariff(hour: int, minute: int = 0) -> bool:
    """Vrátí True, pokud čas (hodina, minuta) spadá do nízkého tarifu."""
    t = hour * 60 + minute
    for start, end in LOW_TARIFF_PERIODS:
        a, b = _minutes(start), _minutes(end) or 24 * 60
        if (a <= t < b) if a < b else (t >= a or t < b):  # úsek přes půlnoc
            return True
    return False


def total_price_kwh(spot_kwh: float, low_tariff: bool) -> float:
    """Koncová cena v Kč/kWh pro spotovou cenu v Kč/kWh (bez DPH)."""
    return spot_kwh * VAT + (FIXED_NT if low_tariff else FIXED_VT)


def sell_price_kwh(spot_kwh: float) -> float:
    """Výkupní cena v Kč/kWh: spot bez DPH minus poplatek dodavatele za výkup."""
    return spot_kwh - SELL_FEE


def low_tariff_price(spot_kwh: float) -> float:
    """Cena v nízkém tarifu (senzor „Nízký tarif cena")."""
    return round(total_price_kwh(spot_kwh, low_tariff=True), 4)


def high_tariff_price(spot_kwh: float) -> float:
    """Cena ve vysokém tarifu (senzor „Vysoký tarif cena")."""
    return round(total_price_kwh(spot_kwh, low_tariff=False), 4)


def czk_mwh_to_kwh(price_czk_mwh: float) -> float:
    """Převod CZK/MWh → Kč/kWh."""
    return price_czk_mwh / 1000


def compute_tariff_prices(
    prices: list[tuple[datetime, float]],
) -> list[TariffPrice]:
    """Spočítá koncové ceny pro seznam (čas, spot v CZK/MWh)."""
    result = []
    for time_from, price_czk_mwh in prices:
        spot_kwh = czk_mwh_to_kwh(price_czk_mwh)
        low = is_low_tariff(time_from.hour, time_from.minute)
        result.append(TariffPrice(
            time_from=time_from,
            spot_kwh=spot_kwh,
            is_low_tariff=low,
            total_kwh=total_price_kwh(spot_kwh, low),
        ))
    return result


# Odchylka od průměru srovnávacích cen, od které je cena „vysoká" / „nízká"
LEVEL_TOLERANCE = 0.15


def price_level(current: float, references: list[float]) -> str | None:
    """Zhodnotí cenu vůči průměru srovnávacích cen: „nízká" / „normální" / „vysoká"."""
    if not references:
        return None
    avg = sum(references) / len(references)
    if current > avg * (1 + LEVEL_TOLERANCE):
        return "vysoká"
    if current < avg * (1 - LEVEL_TOLERANCE):
        return "nízká"
    return "normální"
