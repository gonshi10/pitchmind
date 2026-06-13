"""Build the entity index: competitions, seasons, players, teams, and aliases."""

from __future__ import annotations

import unicodedata

import duckdb

from .. import config
from . import catalog

# Curated nicknames not derivable from official names.
TEAM_NICKNAMES: dict[str, list[str]] = {
    "Barcelona": ["Barca", "Barça", "FC Barcelona", "Barcelona FC"],
    "Real Madrid": ["Madrid", "Los Blancos"],
    "Atlético Madrid": ["Atletico", "Atleti", "Atletico Madrid", "Atlético"],
    "Athletic Club": ["Athletic Bilbao", "Bilbao"],
    "Real Sociedad": ["La Real", "Sociedad"],
    "Real Betis": ["Betis"],
    "Sevilla": ["Sevilla FC"],
    "Valencia": ["Valencia CF"],
    "Celta Vigo": ["Celta"],
    "Deportivo La Coruña": ["Deportivo", "Depor"],
    "Sporting Gijón": ["Sporting"],
    "Rayo Vallecano": ["Rayo"],
    "France": ["Les Bleus"],
    "Germany": ["Die Mannschaft"],
    "Brazil": ["Seleção"],
    "Argentina": ["Albiceleste"],
}

PLAYER_NICKNAMES: list[tuple[str, list[str]]] = [
    ("suarez diaz", ["Luis Suárez", "Luis Suarez", "Lucho"]),
    ("ronaldo dos santos", ["Cristiano", "Cristiano Ronaldo", "CR7"]),
    ("messi cuccittini", ["Leo Messi", "Lionel Messi"]),
    ("neymar da silva", ["Neymar"]),
    ("gareth", ["Gareth Bale", "Bale"]),
    ("james rodriguez", ["James"]),
    ("luis alarcon", ["Isco"]),
    ("francisco roman alarcon", ["Isco"]),
    ("kilian mbappe", ["Mbappe", "Mbappé", "Kylian"]),
    ("harry kane", ["Kane"]),
    ("robert lewandowski", ["Lewandowski", "Lewy"]),
]

_PARTICLES = {"de", "del", "la", "las", "los", "da", "dos", "do", "i", "y", "van", "von"}


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str) -> str:
    return " ".join(strip_accents(text).lower().split())


def _player_nicknames(name: str) -> set[str]:
    norm = normalize(name)
    out: set[str] = set()
    for ident, aliases in PLAYER_NICKNAMES:
        if ident in norm:
            for a in aliases:
                out.add(a)
                out.add(strip_accents(a))
    return out


def _alias_variants(name: str) -> set[str]:
    variants = {name, strip_accents(name)}
    for tok in name.split():
        if len(tok) >= 4 and tok.lower() not in _PARTICLES:
            variants.add(tok)
            variants.add(strip_accents(tok))
    for nick in TEAM_NICKNAMES.get(name, []):
        variants.add(nick)
        variants.add(strip_accents(nick))
    return {v for v in variants if v}


def _build_catalog_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Populate competitions and seasons from the cached catalog."""
    df = catalog.read_catalog()
    con.execute("DROP TABLE IF EXISTS competitions")
    con.execute(
        """
        CREATE TABLE competitions (
            competition_id BIGINT,
            competition_name TEXT,
            country_name TEXT,
            competition_gender TEXT,
            competition_international BOOLEAN
        )
        """
    )
    comp_rows = []
    seen: set[int] = set()
    for _, row in df.iterrows():
        cid = int(row["competition_id"])
        if cid in seen:
            continue
        seen.add(cid)
        comp_rows.append(
            (
                cid,
                str(row["competition_name"]),
                str(row.get("country_name", "")),
                str(row.get("competition_gender", "")),
                bool(row.get("competition_international", False)),
            )
        )
    con.executemany(
        "INSERT INTO competitions VALUES (?, ?, ?, ?, ?)", comp_rows
    )

    con.execute("DROP TABLE IF EXISTS seasons")
    con.execute(
        """
        CREATE TABLE seasons (
            competition_id BIGINT,
            season_id BIGINT,
            season_name TEXT,
            label TEXT
        )
        """
    )
    season_rows = [
        (
            int(row["competition_id"]),
            int(row["season_id"]),
            str(row["season_name"]),
            f"{row['competition_name']} {row['season_name']}",
        )
        for _, row in df.iterrows()
    ]
    con.executemany("INSERT INTO seasons VALUES (?, ?, ?, ?)", season_rows)


def build(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Create entity tables and aliases from events + catalog."""
    own = con is None
    if con is None:
        con = duckdb.connect(str(config.DB_PATH), read_only=False)

    try:
        _build_catalog_tables(con)

        con.execute("DROP TABLE IF EXISTS teams")
        con.execute(
            """
            CREATE TABLE teams AS
            SELECT team_id, competition_id, season_id,
                   any_value(team) AS team_name,
                   count(*) AS events_n
            FROM events
            WHERE team_id IS NOT NULL
            GROUP BY team_id, competition_id, season_id
            """
        )

        con.execute("DROP TABLE IF EXISTS players")
        con.execute(
            """
            CREATE TABLE players AS
            WITH totals AS (
                SELECT player_id, competition_id, season_id, count(*) AS events_n
                FROM events
                WHERE player_id IS NOT NULL
                GROUP BY player_id, competition_id, season_id
            ),
            ranked AS (
                SELECT player_id, competition_id, season_id,
                       player AS player_name, team AS team_name, team_id,
                       row_number() OVER (
                           PARTITION BY player_id, competition_id, season_id
                           ORDER BY count(*) DESC
                       ) AS rk
                FROM events
                WHERE player_id IS NOT NULL
                GROUP BY player_id, competition_id, season_id,
                         player, team, team_id
            )
            SELECT r.player_id, r.competition_id, r.season_id,
                   r.player_name, r.team_name, r.team_id, t.events_n
            FROM ranked r
            JOIN totals t
              ON r.player_id = t.player_id
             AND r.competition_id = t.competition_id
             AND r.season_id = t.season_id
            WHERE r.rk = 1
            """
        )

        players = con.execute(
            "SELECT player_id, competition_id, season_id, player_name "
            "FROM players"
        ).fetchall()
        teams = con.execute(
            "SELECT team_id, competition_id, season_id, team_name FROM teams"
        ).fetchall()
        seasons = con.execute(
            "SELECT competition_id, season_id, label FROM seasons"
        ).fetchall()
        competitions = con.execute(
            "SELECT competition_id, competition_name FROM competitions"
        ).fetchall()

        rows: list[tuple] = []

        def add_alias(
            kind: str,
            entity_id: int,
            name: str,
            alias: str,
            competition_id: int | None = None,
            season_id: int | None = None,
        ) -> None:
            rows.append(
                (
                    kind,
                    entity_id,
                    name,
                    alias,
                    normalize(alias),
                    competition_id,
                    season_id,
                )
            )

        for pid, comp_id, season_id, name in players:
            comp_id, season_id = int(comp_id), int(season_id)
            for alias in _alias_variants(name) | _player_nicknames(name):
                add_alias("player", int(pid), name, alias, comp_id, season_id)

        for tid, comp_id, season_id, name in teams:
            comp_id, season_id = int(comp_id), int(season_id)
            for alias in _alias_variants(name):
                add_alias("team", int(tid), name, alias, comp_id, season_id)

        for comp_id, season_id, label in seasons:
            comp_id, season_id = int(comp_id), int(season_id)
            season_entity_id = comp_id * 100000 + season_id
            for alias in {label, strip_accents(label)}:
                add_alias("season", season_entity_id, label, alias, comp_id, season_id)
            season_part = label.split(" ", 1)[-1] if " " in label else label
            for alias in {season_part, strip_accents(season_part)}:
                add_alias("season", season_entity_id, label, alias, comp_id, season_id)

        for comp_id, comp_name in competitions:
            comp_id = int(comp_id)
            for alias in {comp_name, strip_accents(comp_name)}:
                add_alias("competition", comp_id, comp_name, alias)

        con.execute("DROP TABLE IF EXISTS aliases")
        con.execute(
            """
            CREATE TABLE aliases (
                kind           TEXT,
                entity_id      BIGINT,
                name           TEXT,
                alias          TEXT,
                alias_norm     TEXT,
                competition_id BIGINT,
                season_id      BIGINT
            )
            """
        )
        con.executemany("INSERT INTO aliases VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

        return {
            "competitions": con.execute(
                "SELECT count(*) FROM competitions"
            ).fetchone()[0],
            "seasons": con.execute("SELECT count(*) FROM seasons").fetchone()[0],
            "players": con.execute("SELECT count(*) FROM players").fetchone()[0],
            "teams": con.execute("SELECT count(*) FROM teams").fetchone()[0],
            "aliases": con.execute("SELECT count(*) FROM aliases").fetchone()[0],
        }
    finally:
        if own:
            con.close()
