"""PitchMind command-line interface.

    pitchmind etl download | flatten | load-duckdb | entity-index | marts | all
    pitchmind ask "<question>" [--show-sql] [--show-trace]
    pitchmind eval [--limit N]

ETL commands are network/DuckDB only and don't need an API key. ``ask``/``eval`` import the
agent lazily so the ETL path stays importable without ``anthropic`` configured.
"""

from __future__ import annotations

import json

import typer

from . import config

app = typer.Typer(add_completion=False, help="Natural-language football analytics.")
etl_app = typer.Typer(help="Offline data pipeline (StatsBomb -> DuckDB).")
app.add_typer(etl_app, name="etl")


# --------------------------------------------------------------------------- ETL
@etl_app.command("download")
def etl_download() -> None:
    """Verify the target competition/season and cache the match list."""
    from .etl import download

    matches = download.download_matches()
    typer.echo(f"Verified {config.TARGET.label}. Cached {len(matches)} matches.")


@etl_app.command("flatten")
def etl_flatten() -> None:
    """Fetch each match's events and write curated parquet (one file per match)."""
    from .etl import download, flatten

    match_ids = download.cached_match_ids()
    total = len(match_ids)
    written = 0
    for i, match_id in enumerate(match_ids, start=1):
        df = flatten.fetch_and_flatten_match(match_id)
        flatten.write_match_parquet(df, match_id)
        written += len(df)
        typer.echo(f"  [{i}/{total}] match {match_id}: {len(df)} events")
    typer.echo(f"Flattened {total} matches, {written} events -> {config.PARQUET_DIR}")


@etl_app.command("load-duckdb")
def etl_load_duckdb() -> None:
    """(Re)build the events table and typed views from parquet."""
    from .etl import load_duckdb

    counts = load_duckdb.load()
    typer.echo(f"Loaded into {config.DB_PATH}:")
    for rel, n in counts.items():
        typer.echo(f"  {rel}: {n}")


@etl_app.command("entity-index")
def etl_entity_index() -> None:
    """Build players, teams, and aliases."""
    from .etl import entity_index

    counts = entity_index.build()
    typer.echo("Entity index:")
    for rel, n in counts.items():
        typer.echo(f"  {rel}: {n}")


@etl_app.command("marts")
def etl_marts() -> None:
    """Materialize mart_shots and mart_player_season."""
    from .etl import marts

    counts = marts.build()
    typer.echo("Marts:")
    for rel, n in counts.items():
        typer.echo(f"  {rel}: {n}")


@etl_app.command("all")
def etl_all() -> None:
    """Run the whole ETL chain in order."""
    etl_download()
    etl_flatten()
    etl_load_duckdb()
    etl_entity_index()
    etl_marts()


# --------------------------------------------------------------------------- ASK
@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="A football question in plain English."),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print the generated SQL."),
    show_trace: bool = typer.Option(
        False, "--show-trace", help="Print the full agent trace as JSON."
    ),
) -> None:
    """Ask PitchMind a question."""
    from .agent.loop import run

    try:
        result = run(question)
    except RuntimeError as exc:  # e.g. missing ANTHROPIC_API_KEY
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    typer.echo("")
    typer.echo(result.answer)
    if result.viz_path:
        typer.echo(f"\n[viz] {result.viz_path}")
    if show_sql and result.sql:
        typer.echo("\n--- SQL ---")
        typer.echo(result.sql)
    if show_trace:
        typer.echo("\n--- TRACE ---")
        typer.echo(json.dumps(result.trace, indent=2, default=str))


# -------------------------------------------------------------------------- EVAL
@app.command("eval")
def eval_cmd(
    limit: int = typer.Option(0, "--limit", help="Only run the first N gold items."),
) -> None:
    """Run the gold-set eval (the Phase 1 ship gate)."""
    from .eval_runner import run_eval

    try:
        ok = run_eval(limit=limit or None)
    except RuntimeError as exc:  # e.g. missing ANTHROPIC_API_KEY
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    raise typer.Exit(code=0 if ok else 1)


if __name__ == "__main__":
    app()
