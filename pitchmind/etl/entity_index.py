"""Build the entity index: players, teams, and an alias table for fuzzy resolution.

Aliases cover full name, accent-stripped name, and last-name-only, each with a normalized
(lowercased, accent-free) form that ``rapidfuzz`` matches extracted names against.
"""

from __future__ import annotations

import unicodedata

import duckdb

from .. import config


def strip_accents(text: str) -> str:
    """'Sergio Busquets i Burgos' -> ascii; 'Iñaki' -> 'Inaki'."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Lowercased, accent-free, whitespace-collapsed form for matching."""
    return " ".join(strip_accents(text).lower().split())


# Curated nicknames that aren't derivable from the official name by tokenizing.
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
}

# Curated short-name aliases for well-known players whose common name is ambiguous by
# surname alone (e.g. several "Suárez"). Keyed by a distinctive normalized substring of the
# full StatsBomb name; matched players get these exact aliases so short queries resolve to
# the intended star. Identity comes from the data, not hard-coded ids.
PLAYER_NICKNAMES: list[tuple[str, list[str]]] = [
    ("suarez diaz", ["Luis Suárez", "Luis Suarez", "Lucho"]),
    ("ronaldo dos santos", ["Cristiano", "Cristiano Ronaldo", "CR7"]),
    ("messi cuccittini", ["Leo Messi", "Lionel Messi"]),
    ("neymar da silva", ["Neymar"]),
    ("gareth", ["Gareth Bale", "Bale"]),
    ("james rodriguez", ["James"]),
    ("luis alarcon", ["Isco"]),
    ("francisco roman alarcon", ["Isco"]),
]

# Spanish naming particles that are never a usable surname on their own.
_PARTICLES = {"de", "del", "la", "las", "los", "da", "dos", "do", "i", "y", "van", "von"}


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
    """Generate alias surface forms for a player/team name.

    Includes the full name and *every* meaningful token (not just first/last) so
    two-surname Spanish names resolve on the commonly-used surname — e.g.
    'Luis Alberto Suárez Díaz' yields 'Suárez' even though its last token is 'Díaz'.
    """
    variants = {name, strip_accents(name)}
    for tok in name.split():
        if len(tok) >= 4 and tok.lower() not in _PARTICLES:
            variants.add(tok)
            variants.add(strip_accents(tok))
    for nick in TEAM_NICKNAMES.get(name, []):
        variants.add(nick)
        variants.add(strip_accents(nick))
    return {v for v in variants if v}


def build(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Create ``players``, ``teams``, and ``aliases`` from the events table."""
    own = con is None
    if con is None:
        con = duckdb.connect(str(config.DB_PATH), read_only=False)

    try:
        # teams (events_n = prominence, for resolution tiebreaks)
        con.execute("DROP TABLE IF EXISTS teams")
        con.execute(
            """
            CREATE TABLE teams AS
            SELECT team_id, any_value(team) AS team_name, count(*) AS events_n
            FROM events
            WHERE team_id IS NOT NULL
            GROUP BY team_id
            """
        )

        # players (most-common team for context; events_n = prominence)
        con.execute("DROP TABLE IF EXISTS players")
        con.execute(
            """
            CREATE TABLE players AS
            WITH totals AS (
                SELECT player_id, count(*) AS events_n
                FROM events WHERE player_id IS NOT NULL GROUP BY player_id
            ),
            ranked AS (
                SELECT player_id, player AS player_name, team AS team_name, team_id,
                       row_number() OVER (
                           PARTITION BY player_id ORDER BY count(*) DESC
                       ) AS rk
                FROM events
                WHERE player_id IS NOT NULL
                GROUP BY player_id, player, team, team_id
            )
            SELECT r.player_id, r.player_name, r.team_name, r.team_id, t.events_n
            FROM ranked r JOIN totals t USING (player_id)
            WHERE r.rk = 1
            """
        )

        # aliases (built in Python, written back)
        players = con.execute(
            "SELECT player_id, player_name FROM players"
        ).fetchall()
        teams = con.execute("SELECT team_id, team_name FROM teams").fetchall()

        rows: list[tuple[str, int, str, str, str]] = []
        for pid, name in players:
            aliases = _alias_variants(name) | _player_nicknames(name)
            for alias in aliases:
                rows.append(("player", int(pid), name, alias, normalize(alias)))
        for tid, name in teams:
            for alias in _alias_variants(name):
                rows.append(("team", int(tid), name, alias, normalize(alias)))

        con.execute("DROP TABLE IF EXISTS aliases")
        con.execute(
            """
            CREATE TABLE aliases (
                kind       TEXT,
                entity_id  BIGINT,
                name       TEXT,
                alias      TEXT,
                alias_norm TEXT
            )
            """
        )
        con.executemany(
            "INSERT INTO aliases VALUES (?, ?, ?, ?, ?)", rows
        )

        return {
            "players": con.execute("SELECT count(*) FROM players").fetchone()[0],
            "teams": con.execute("SELECT count(*) FROM teams").fetchone()[0],
            "aliases": con.execute("SELECT count(*) FROM aliases").fetchone()[0],
        }
    finally:
        if own:
            con.close()
