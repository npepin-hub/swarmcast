"""Polymarket Gamma API — read-only market data.
Only called AFTER the swarm vote is sealed. Never touched during deliberation.
"""
from __future__ import annotations
import httpx
from ..schemas import MarketSnapshot

_GAMMA_BASE = "https://gamma-api.polymarket.com"

_FIFA_NAMES = {
    "ARG": "Argentina",     "BRA": "Brazil",        "FRA": "France",
    "ENG": "England",       "ESP": "Spain",         "GER": "Germany",
    "ITA": "Italy",         "POR": "Portugal",      "NED": "Netherlands",
    "BEL": "Belgium",       "URU": "Uruguay",       "MEX": "Mexico",
    "USA": "United States", "CAN": "Canada",        "MAR": "Morocco",
    "SEN": "Senegal",       "JPN": "Japan",         "KOR": "South Korea",
    "AUS": "Australia",     "NGA": "Nigeria",       "CRO": "Croatia",
    "SUI": "Switzerland",   "DEN": "Denmark",       "POL": "Poland",
    "SWE": "Sweden",        "COL": "Colombia",      "CHI": "Chile",
    "ECU": "Ecuador",       "PER": "Peru",          "PAR": "Paraguay",
    "BOL": "Bolivia",       "VEN": "Venezuela",     "CRC": "Costa Rica",
    "PAN": "Panama",        "HON": "Honduras",      "GTM": "Guatemala",
    "CMR": "Cameroon",      "GHA": "Ghana",         "CIV": "Ivory Coast",
    "MLI": "Mali",          "TUN": "Tunisia",       "EGY": "Egypt",
    "ALG": "Algeria",       "RSA": "South Africa",  "IRN": "Iran",
    "SAU": "Saudi Arabia",  "QAT": "Qatar",         "UAE": "UAE",
    "CHN": "China",         "THA": "Thailand",      "VIE": "Vietnam",
    "NZL": "New Zealand",   "SRB": "Serbia",        "SVK": "Slovakia",
    "CZE": "Czech Republic","AUT": "Austria",       "HUN": "Hungary",
    "ROU": "Romania",       "UKR": "Ukraine",       "TUR": "Turkey",
    "SCO": "Scotland",      "WAL": "Wales",         "NIR": "Northern Ireland",
    "GRE": "Greece",        "NOR": "Norway",        "FIN": "Finland",
    "RUS": "Russia",        "ISL": "Iceland",       "IRL": "Ireland",
}


def get_market_snapshot(market_id: str) -> MarketSnapshot:
    """Fetch current implied probability and volume for a Polymarket market."""
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{_GAMMA_BASE}/markets/{market_id}")
        r.raise_for_status()
        data = r.json()

    # Gamma API returns outcomePrices as a JSON-encoded list e.g. '["0.64", "0.36"]'
    import json as _json
    prices = _json.loads(data.get("outcomePrices", '["0.5", "0.5"]'))
    market_p = float(prices[0])   # index 0 = "Yes" / team A wins

    return MarketSnapshot(
        market_id=market_id,
        market_probability=market_p,
        volume_24h=data.get("volume24hr"),
        open_interest=data.get("openInterest"),
    )


def find_wc_market(team_a: str, team_b: str) -> str | None:
    """Search for an active WC match market. Returns market_id or None."""
    name_a = _FIFA_NAMES.get(team_a.upper(), team_a).lower()
    name_b = _FIFA_NAMES.get(team_b.upper(), team_b).lower()

    with httpx.Client(timeout=10) as c:
        r = c.get(
            f"{_GAMMA_BASE}/markets",
            params={"active": "true", "q": f"{team_a} {team_b}", "limit": 50},
        )
        r.raise_for_status()
        markets = r.json()

    for m in markets:
        title = m.get("question", "").lower()
        if name_a in title and name_b in title:
            return m["id"]
    return None
