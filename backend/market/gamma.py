"""Polymarket Gamma API — read-only market data.
Only called AFTER the swarm vote is sealed. Never touched during deliberation.
"""
from __future__ import annotations
import json as _json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

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

# Reverse: team name (lower) → Polymarket slug code (lower FIFA code)
_NAME_TO_CODE: dict[str, str] = {v.lower(): k.lower() for k, v in _FIFA_NAMES.items()}
_NAME_TO_CODE.update({
    "south africa": "rsa", "korea republic": "kor", "north korea": "prk",
    "ivory coast": "civ",  "cape verde": "cpv",     "congo dr": "cod",
    "bosnia-herzegovina": "bih", "bosnia": "bih",   "czechia": "cze",
    "turkiye": "tur",      "curacao": "cuw",         "united states": "usa",
})


def get_match_markets(team_a: str, team_b: str, match_date: str) -> "MatchMarkets | None":
    """Fetch 3-way match outcome markets for a WC2026 game.
    match_date: ISO date string e.g. '2026-06-11'. Returns None if not yet on Polymarket.
    """
    from dataclasses import dataclass

    code_a = _NAME_TO_CODE.get(team_a.lower(), team_a[:3].lower())
    code_b = _NAME_TO_CODE.get(team_b.lower(), team_b[:3].lower())
    slug = f"fifwc-{code_a}-{code_b}-{match_date}"

    with httpx.Client(timeout=10) as c:
        r = c.get(f"{_GAMMA_BASE}/events", params={"slug": slug})
        if r.status_code != 200 or not r.json():
            return None
        event = r.json()[0]

    mkt = {m["slug"]: m for m in event.get("markets", [])}

    def _price(s: str) -> float:
        m = mkt.get(s)
        if not m:
            return 0.0
        return float(_json.loads(m.get("outcomePrices", '["0","1"]'))[0])

    def _mid(s: str) -> str:
        return mkt.get(s, {}).get("id", "")

    slug_a, slug_d, slug_b = f"{slug}-{code_a}", f"{slug}-draw", f"{slug}-{code_b}"
    return MatchMarkets(
        event_slug=slug, team_a=team_a, team_b=team_b,
        team_a_win=_price(slug_a), draw=_price(slug_d), team_b_win=_price(slug_b),
        volume_24h=event.get("volume24hr", 0.0),
        team_a_market_id=_mid(slug_a), draw_market_id=_mid(slug_d), team_b_market_id=_mid(slug_b),
    )


class MatchMarkets:
    __slots__ = ("event_slug","team_a","team_b","team_a_win","draw","team_b_win",
                 "volume_24h","team_a_market_id","draw_market_id","team_b_market_id")
    def __init__(self, event_slug, team_a, team_b, team_a_win, draw, team_b_win,
                 volume_24h=0.0, team_a_market_id="", draw_market_id="", team_b_market_id=""):
        self.event_slug=event_slug; self.team_a=team_a; self.team_b=team_b
        self.team_a_win=team_a_win; self.draw=draw; self.team_b_win=team_b_win
        self.volume_24h=volume_24h; self.team_a_market_id=team_a_market_id
        self.draw_market_id=draw_market_id; self.team_b_market_id=team_b_market_id

    def model_dump(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def get_market_snapshot(market_id: str) -> MarketSnapshot:
    """Fetch current implied probability and volume for a Polymarket market."""
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{_GAMMA_BASE}/markets/{market_id}")
        r.raise_for_status()
        data = r.json()

    prices = _json.loads(data.get("outcomePrices", '["0.5", "0.5"]'))
    market_p = float(prices[0])   # index 0 = "Yes" / team A wins

    return MarketSnapshot(
        market_id=market_id,
        market_probability=market_p,
        volume_24h=data.get("volume24hr"),
        open_interest=data.get("openInterest"),
    )


# Static map — Polymarket WC2026 winner market IDs (one per qualified team)
_WC26_WINNER_IDS: dict[str, str] = {
    "spain": "558934", "england": "558935", "france": "558936",
    "brazil": "558937", "argentina": "558938", "germany": "558939",
    "portugal": "558940", "netherlands": "558941", "holland": "558941",
    "italy": "558942", "usa": "558943", "united states": "558943",
    "uruguay": "558944", "mexico": "558945", "belgium": "558946",
    "colombia": "558947", "peru": "558948", "japan": "558949",
    "norway": "558951", "canada": "558952", "tunisia": "558954",
    "ecuador": "558955", "paraguay": "558956", "new zealand": "558957",
    "australia": "558958", "iran": "558959", "uzbekistan": "558960",
    "south korea": "558961", "korea": "558961", "jordan": "558962",
    "morocco": "558963", "south africa": "558964", "senegal": "558965",
    "ivory coast": "558966", "cote d'ivoire": "558966", "ghana": "558967",
    "egypt": "558968", "algeria": "558969", "cape verde": "558970",
    "qatar": "558971", "saudi arabia": "558972", "scotland": "558973",
    "switzerland": "558974", "austria": "558975", "croatia": "558976",
    "haiti": "558977", "curacao": "558978", "panama": "558979",
    "sweden": "558980", "congo dr": "558981", "iraq": "558982",
    "bosnia": "558983", "bosnia-herzegovina": "558983", "czechia": "558984",
    "czech republic": "558984", "turkiye": "558985", "turkey": "558985",
}


def find_winner_market(team: str) -> str | None:
    """Look up the WC2026 tournament winner market ID for a team."""
    return _WC26_WINNER_IDS.get(team.lower().strip())


def fetch_winner_odds(team_a: str, team_b: str) -> dict[str, MarketSnapshot]:
    """Return tournament winner market snapshots for both teams (whichever exist)."""
    result = {}
    for team in [team_a, team_b]:
        mid = find_winner_market(team)
        if mid:
            result[team] = get_market_snapshot(mid)
    return result


def fetch_top_wc_favorites(n: int = 5) -> list[dict]:
    """Return the top-n WC2026 winner markets by current probability (parallel fetch)."""
    # deduplicate while preserving insertion order; skip "Any Other Team" market
    unique_ids = [mid for mid in dict.fromkeys(_WC26_WINNER_IDS.values())
                  if mid != "558953"]

    def _fetch(mid: str) -> dict | None:
        try:
            with httpx.Client(timeout=8) as c:
                r = c.get(f"{_GAMMA_BASE}/markets/{mid}")
                if r.status_code != 200:
                    return None
                d = r.json()
            prices = _json.loads(d.get("outcomePrices", '["0","1"]'))
            p = float(prices[0])
            if p <= 0:
                return None
            return {
                "team": d["question"].split("Will ")[1].split(" win")[0],
                "probability": p,
                "market_id": mid,
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = [r for r in pool.map(_fetch, unique_ids) if r is not None]

    results.sort(key=lambda x: x["probability"], reverse=True)
    return results[:n]


_COUNTRY_TO_FIFA = {name.lower(): code for code, name in _FIFA_NAMES.items()}


def build_wc_event_slug(home_code: str, away_code: str, match_date: str) -> str:
    """Polymarket WC match event slug, e.g. fifwc-fra-sen-2026-06-16."""
    return f"fifwc-{home_code.lower()}-{away_code.lower()}-{match_date}"


def fetch_event_by_slug(slug: str) -> dict | None:
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{_GAMMA_BASE}/events", params={"slug": slug})
        r.raise_for_status()
        events = r.json()
    return events[0] if events else None


def _team_label(team: str) -> str:
    """Strip flag emoji prefix; return country name for matching."""
    parts = team.strip().split()
    if len(parts) >= 2 and len(parts[0]) <= 4:
        return " ".join(parts[1:])
    return team.strip()


def moneyline_market_for_team_a(event: dict, team_a: str) -> str | None:
    """Return Gamma market id for 'team A wins' within a match event."""
    label = _team_label(team_a).lower()
    for m in event.get("markets", []):
        git = (m.get("groupItemTitle") or "").lower()
        if git == label or label in git:
            return m.get("id")
        q = (m.get("question") or "").lower()
        if label in q and "win" in q:
            return m.get("id")
    return None


def resolve_wc_moneyline_market(
    team_a: str,
    team_b: str,
    *,
    polymarket_market_id: str = "",
    match_date: str = "",
    home_team_code: str = "",
    away_team_code: str = "",
) -> tuple[str, str]:
    """
    Resolve Polymarket moneyline market id for P(team_a wins).
    Returns (market_id, event_slug_attempted).
    """
    if polymarket_market_id:
        return polymarket_market_id, ""

    if match_date and home_team_code and away_team_code:
        slug = build_wc_event_slug(home_team_code, away_team_code, match_date)
        event = fetch_event_by_slug(slug)
        if event:
            mid = moneyline_market_for_team_a(event, team_a)
            if mid:
                return mid, slug

    mid = find_wc_market(team_a, team_b)
    return (mid or ""), ""


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
