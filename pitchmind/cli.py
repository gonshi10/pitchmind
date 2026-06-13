"""PitchMind command-line interface.

    pitchmind etl catalog | list | add | all
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


def _resolve_add_target(
    competition_id: int | None,
    season_id: int | None,
    name: str | None,
) -> config.Target:
    from .etl import catalog

    if name:
        return catalog.resolve_target(name)
    if competition_id is not None and season_id is not None:
        return catalog.get_target(competition_id, season_id)
    return config.DEFAULT_TARGET


# --------------------------------------------------------------------------- ETL
@etl_app.command("catalog")
def etl_catalog() -> None:
    """Sync the full StatsBomb open-data catalog to data/raw/catalog.parquet."""
    from .etl import catalog

    n = catalog.sync_catalog()
    typer.echo(f"Synced {n} competition/season targets to {config.CATALOG_PATH}")


@etl_app.command("list")
def etl_list() -> None:
    """Show catalog targets and which are loaded locally."""
    from .etl import catalog

    if not config.CATALOG_PATH.exists():
        typer.echo("No catalog cached. Run `pitchmind etl catalog` first.")
        raise typer.Exit(code=1)

    loaded_keys = {
        (t.competition_id, t.season_id) for t in catalog.loaded_targets()
    }
    typer.echo(f"Catalog: {len(catalog.all_targets())} targets")
    typer.echo(f"Loaded:  {len(loaded_keys)} targets\n")
    for target in catalog.all_targets():
        key = (target.competition_id, target.season_id)
        mark = "loaded" if key in loaded_keys else "—"
        stats = catalog.target_stats(target) if key in loaded_keys else {}
        extra = ""
        if stats.get("match_count"):
            extra = f" ({stats['match_count']} matches"
            if stats.get("event_count") is not None:
                extra += f", {stats['event_count']} events"
            extra += ")"
        typer.echo(
            f"  [{mark:6}] {target.label}  "
            f"(competition_id={target.competition_id}, season_id={target.season_id})"
            f"{extra}"
        )


@etl_app.command("add")
def etl_add(
    competition_id: int | None = typer.Option(
        None, "--competition-id", help="StatsBomb competition_id."
    ),
    season_id: int | None = typer.Option(
        None, "--season-id", help="StatsBomb season_id."
    ),
    name: str | None = typer.Option(
        None, "--name", help="Fuzzy label, e.g. 'World Cup 2018'."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-fetch and overwrite existing match parquet."
    ),
) -> None:
    """Download, flatten, and load one competition/season."""
    from .etl import pipeline

    target = _resolve_add_target(competition_id, season_id, name)
    typer.echo(f"Ingesting {target.label} ...")
    result = pipeline.ingest_target(target, force=force)
    typer.echo(
        f"Done: {result['matches']} matches, "
        f"{result['events_flattened']} events flattened."
    )


@etl_app.command("download")
def etl_download(
    competition_id: int | None = typer.Option(None, "--competition-id"),
    season_id: int | None = typer.Option(None, "--season-id"),
    name: str | None = typer.Option(None, "--name"),
) -> None:
    """Alias for ``etl add`` (backward compatible)."""
    etl_add(
        competition_id=competition_id,
        season_id=season_id,
        name=name,
        force=False,
    )


@etl_app.command("flatten")
def etl_flatten(
    competition_id: int | None = typer.Option(None, "--competition-id"),
    season_id: int | None = typer.Option(None, "--season-id"),
    name: str | None = typer.Option(None, "--name"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Flatten cached matches for one target (run ``etl add`` or download first)."""
    from .etl import flatten

    target = _resolve_add_target(competition_id, season_id, name)
    match_count, event_count = flatten.flatten_target(target, force=force)
    typer.echo(
        f"Flattened {match_count} matches, {event_count} events for {target.label}"
    )


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
    """Build competitions, seasons, players, teams, and aliases."""
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
def etl_all(
    everything: bool = typer.Option(
        False,
        "--everything",
        help="Download and ingest every catalog target (hours; large disk).",
    ),
    force: bool = typer.Option(False, "--force", help="Re-flatten existing matches."),
) -> None:
    """Rebuild derived tables, or ingest all catalog targets with --everything."""
    from .etl import catalog, pipeline

    if everything:
        if not config.CATALOG_PATH.exists():
            catalog.sync_catalog()
        targets = catalog.all_targets()
        typer.echo(f"Ingesting {len(targets)} catalog targets ...")
        for i, target in enumerate(targets, start=1):
            typer.echo(f"\n[{i}/{len(targets)}] {target.label}")
            try:
                result = pipeline.ingest_target(target, force=force)
                typer.echo(
                    f"  {result['matches']} matches, "
                    f"{result['events_flattened']} events"
                )
            except Exception as exc:  # noqa: BLE001 — continue bulk ingest on failure
                typer.secho(f"  FAILED: {exc}", fg=typer.colors.RED)
        typer.echo("\nBulk ingest complete.")
        return

    result = pipeline.rebuild_derived()
    typer.echo("Rebuilt from parquet:")
    for stage, counts in result.items():
        typer.echo(f"  {stage}:")
        for rel, n in counts.items():
            typer.echo(f"    {rel}: {n}")


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
    except RuntimeError as exc:
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


# ------------------------------------------------------------------------- SERVE
@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
) -> None:
    """Run the FastAPI backend (requires the [api] extra)."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise typer.BadParameter(
            "API deps missing. Install with: pip install -e '.[api]'"
        ) from exc

    uvicorn.run("api.main:app", host=host, port=port, reload=reload)


# -------------------------------------------------------------------------- EVAL
@app.command("eval")
def eval_cmd(
    limit: int = typer.Option(0, "--limit", help="Only run the first N gold items."),
    breadth: bool = typer.Option(
        False, "--breadth", help="Run gold_breadth.jsonl instead of gold_core.jsonl."
    ),
) -> None:
    """Run the gold-set eval (the Phase 1 ship gate)."""
    from .eval_runner import run_eval

    gold_file = "gold_breadth.jsonl" if breadth else "gold_core.jsonl"
    try:
        ok = run_eval(gold_file=gold_file, limit=limit or None)
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    raise typer.Exit(code=0 if ok else 1)


if __name__ == "__main__":
    app()
