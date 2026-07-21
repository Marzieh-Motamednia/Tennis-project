"""
build_tennis_db.py

Builds a DuckDB analytical database from many tiny tennis Parquet files.

Main properties:
- Does not delete or deduplicate any rows.
- Adds snapshot_date and source_file to every imported row.
- Imports files in batches to keep RAM usage controlled.
- Searches recursively for date folders such as:
      1-2-2024
      01-02-2024
      1_2_2024
      1.2.2024
      1 2 2024
- Supports date directories whose path eventually contains:
      data/raw/raw_match_parquet/
      data/raw/raw_odds_parquet/
      data/raw/raw_point_by_point_parquet/
      data/raw/raw_statistics_parquet/
      data/raw/raw_tennis_power_parquet/
      data/raw/raw_votes_parquet/
- Creates audit tables for files and imported row counts.

Usage:
    python build_tennis_db.py

Optional:
    python build_tennis_db.py --root "D:\\tennis_data"
    python build_tennis_db.py --output "D:\\output\\tennis.duckdb"
    python build_tennis_db.py --batch-size 500
    python build_tennis_db.py --overwrite

Important:
- Without --overwrite, an existing output database is not modified.
- The script intentionally performs no deduplication.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import duckdb


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATE_FOLDER_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})[-_. ](?P<month>\d{1,2})[-_. ](?P<year>\d{4})$"
)

EXPECTED_START_DATE = date(2024, 2, 1)
EXPECTED_END_DATE = date(2024, 3, 31)

DEFAULT_DATABASE_NAME = "tennis.duckdb"
DEFAULT_BATCH_SIZE = 500

# DuckDB settings appropriate for a machine with 8 GB RAM.
DEFAULT_MEMORY_LIMIT = "5GB"
DEFAULT_THREADS = 4
DEFAULT_TEMP_DIRECTORY = "duckdb_temp"


@dataclass(frozen=True)
class TableRule:
    source_directory: str
    file_key: str
    target_table: str


TABLE_RULES: tuple[TableRule, ...] = (
    # raw_match_parquet
    TableRule("raw_match_parquet", "event", "match_event"),
    TableRule("raw_match_parquet", "away_team", "match_away_team"),
    TableRule("raw_match_parquet", "away_team_score", "match_away_score"),
    TableRule("raw_match_parquet", "home_team", "match_home_team"),
    TableRule("raw_match_parquet", "home_team_score", "match_home_score"),
    TableRule("raw_match_parquet", "round", "match_round"),
    TableRule("raw_match_parquet", "season", "match_season"),
    TableRule("raw_match_parquet", "time", "match_time"),
    TableRule("raw_match_parquet", "tournament", "match_tournament"),
    TableRule("raw_match_parquet", "venue", "match_venue"),

    # Other source directories
    TableRule("raw_odds_parquet", "odds", "odds"),
    TableRule("raw_point_by_point_parquet", "pbp", "game_point_by_point"),
    TableRule("raw_statistics_parquet", "statistics", "period_statistics"),
    TableRule("raw_tennis_power_parquet", "power", "power"),
    TableRule("raw_votes_parquet", "votes", "match_votes"),
)


# Expected columns are used for auditing only.
# They are NOT used to drop columns or force casts.
EXPECTED_COLUMNS: dict[str, set[str]] = {
    "match_event": {
        "match_id",
        "first_to_serve",
        "home_team_seed",
        "away_team_seed",
        "custom_id",
        "winner_code",
        "default_period_count",
        "start_datetime",
        "match_slug",
        "final_result_only",
    },
    "match_votes": {
        "match_id",
        "home_vote",
        "away_vote",
    },
    "match_round": {
        "match_id",
        "round_id",
        "name",
        "slug",
        "cup_round_type",
    },
    "match_home_score": {
        "match_id",
        "current_score",
        "display_score",
        "period_1",
        "period_2",
        "period_3",
        "period_4",
        "period_5",
        "period_1_tie_break",
        "period_2_tie_break",
        "period_3_tie_break",
        "period_4_tie_break",
        "period_5_tie_break",
        "normal_time",
    },
    "odds": {
        "match_id",
        "market_id",
        "market_name",
        "is_live",
        "suspended",
        "initial_fractional_value",
        "fractional_value",
        "choice_name",
        "choice_source_id",
        "winnig",
        "change",
    },
    "period_statistics": {
        "match_id",
        "period",
        "statistic_category_name",
        "statistic_name",
        "home_stat",
        "away_stat",
        "compare_code",
        "statistic_type",
        "value_type",
        "home_value",
        "away_value",
        "home_total",
        "away_total",
    },
    "match_venue": {
        "match_id",
        "city",
        "stadium",
        "venue_id",
        "country",
    },
    "match_away_score": {
        "match_id",
        "current_score",
        "display_score",
        "period_1",
        "period_2",
        "period_3",
        "period_4",
        "period_5",
        "period_1_tie_break",
        "period_2_tie_break",
        "period_3_tie_break",
        "period_4_tie_break",
        "period_5_tie_break",
        "normal_time",
    },
    "power": {
        "match_id",
        "set_num",
        "game_num",
        "value",
        "break_occurred",
    },
    "match_tournament": {
        "match_id",
        "tournament_id",
        "tournament_name",
        "tournament_slug",
        "tournament_unique_id",
        "tournament_category_name",
        "tournament_category_slug",
        "user_count",
        "ground_type",
        "tennis_points",
        "has_event_player_statistics",
        "crowd_sourcing_enabled",
        "has_performance_graph_feature",
        "display_inverse_home_away_teams",
        "priority",
        "competition_type",
    },
    "match_home_team": {
        "match_id",
        "name",
        "slug",
        "gender",
        "user_count",
        "residence",
        "birthplace",
        "height",
        "weight",
        "plays",
        "turned_pro",
        "current_prize",
        "total_prize",
        "player_id",
        "current_rank",
        "name_code",
        "country",
        "full_name",
    },
    "match_time": {
        "match_id",
        "period_1",
        "period_2",
        "period_3",
        "period_4",
        "period_5",
        "current_period_start_timestamp",
    },
    "match_season": {
        "match_id",
        "season_id",
        "name",
        "year",
    },
    "match_away_team": {
        "match_id",
        "name",
        "slug",
        "gender",
        "user_count",
        "residence",
        "birthplace",
        "height",
        "weight",
        "plays",
        "turned_pro",
        "current_prize",
        "total_prize",
        "player_id",
        "current_rank",
        "name_code",
        "country",
        "full_name",
    },
    "game_point_by_point": {
        "match_id",
        "set_id",
        "game_id",
        "point_id",
        "home_point",
        "away_point",
        "point_description",
        "home_point_type",
        "away_point_type",
        "home_score",
    },
}


# Longer keys must be tested first:
# home_team_score must be checked before home_team, etc.
RULES_BY_DIRECTORY: dict[str, list[TableRule]] = defaultdict(list)

for rule in TABLE_RULES:
    RULES_BY_DIRECTORY[rule.source_directory].append(rule)

for directory_name in RULES_BY_DIRECTORY:
    RULES_BY_DIRECTORY[directory_name].sort(
        key=lambda item: len(item.file_key),
        reverse=True,
    )


@dataclass(frozen=True)
class DiscoveredFile:
    path: Path
    snapshot_date: date
    source_directory: str
    file_key: str
    target_table: str


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def quote_identifier(identifier: str) -> str:
    """Safely quote a DuckDB identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def normalize_path(path: Path) -> str:
    """
    Return an absolute path using forward slashes.

    DuckDB handles forward slashes well on Windows, and this also makes
    source_file values more consistent.
    """
    return path.resolve().as_posix()


def chunked(items: list[DiscoveredFile], size: int) -> Iterable[list[DiscoveredFile]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]

DATE_FORMATS = (
    "%Y%m%d",    # 20240201
    "%Y-%m-%d",  # 2024-02-01
    "%Y_%m_%d",  # 2024_02_01
    "%d-%m-%Y",  # 01-02-2024
    "%d_%m_%Y",  # 01_02_2024
)


def parse_date_folder_name(folder_name: str) -> date | None:
    name = folder_name.strip()

    for date_format in DATE_FORMATS:
        try:
            parsed = datetime.strptime(name, date_format).date()
        except ValueError:
            continue

        if EXPECTED_START_DATE <= parsed <= EXPECTED_END_DATE:
            return parsed

    return None



def find_snapshot_date(path: Path, root: Path) -> date | None:
    """
    Walk upward through the path and find the closest valid date directory.
    """
    current = path.parent
    root_resolved = root.resolve()

    while True:
        parsed = parse_date_folder_name(current.name)

        if parsed is not None:
            return parsed

        if current == root_resolved or current.parent == current:
            break

        current = current.parent

    return None


def find_source_directory(path: Path) -> str | None:
    known_directories = set(RULES_BY_DIRECTORY)

    for parent in path.parents:
        name = parent.name.lower()

        if name in known_directories:
            return name

    return None


def file_key_matches(file_stem: str, key: str) -> bool:
    """
    Detect the logical file key in a Parquet filename.

    Supported examples:
        event.parquet
        event_123.parquet
        event-123.parquet
        123_event.parquet
        match_event_123.parquet

    The key must be separated from surrounding text by non-alphanumeric
    characters, or occur at the beginning/end.
    """
    stem = file_stem.lower()

    if stem == key:
        return True

    pattern = rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])"
    return re.search(pattern, stem) is not None


def classify_file(path: Path, source_directory: str) -> TableRule | None:
    rules = RULES_BY_DIRECTORY[source_directory]

    for rule in rules:
        if file_key_matches(path.stem, rule.file_key):
            return rule

    return None


def discover_files(root: Path) -> tuple[list[DiscoveredFile], list[Path], list[Path]]:
    """
    Returns:
        discovered_files
        unclassified_parquet_files
        parquet_files_without_valid_date
    """
    discovered: list[DiscoveredFile] = []
    unclassified: list[Path] = []
    missing_date: list[Path] = []

    print(f"\nScanning recursively under:\n  {root.resolve()}")
    print("This may take a little while because there are many tiny files...\n")

    parquet_count = 0

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".parquet":
            continue

        parquet_count += 1

        if parquet_count % 10_000 == 0:
            print(f"  Scanned {parquet_count:,} Parquet files...")

        source_directory = find_source_directory(path)

        # Ignore Parquet files outside the six known source directories.
        if source_directory is None:
            continue

        snapshot_date = find_snapshot_date(path, root)

        if snapshot_date is None:
            missing_date.append(path)
            continue

        rule = classify_file(path, source_directory)

        if rule is None:
            unclassified.append(path)
            continue

        discovered.append(
            DiscoveredFile(
                path=path,
                snapshot_date=snapshot_date,
                source_directory=source_directory,
                file_key=rule.file_key,
                target_table=rule.target_table,
            )
        )

    discovered.sort(
        key=lambda item: (
            item.target_table,
            item.snapshot_date,
            str(item.path).lower(),
        )
    )

    return discovered, unclassified, missing_date


def initialize_connection(
    database_path: Path,
    memory_limit: str,
    threads: int,
    temp_directory: Path,
) -> duckdb.DuckDBPyConnection:
    temp_directory.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(database_path))

    connection.execute(f"SET memory_limit = '{memory_limit}'")
    connection.execute(f"SET threads = {int(threads)}")
    connection.execute(
        "SET temp_directory = ?",
        [normalize_path(temp_directory)],
    )
    connection.execute("SET preserve_insertion_order = false")

    return connection


def create_metadata_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS _build_info (
            build_started_at TIMESTAMP,
            build_finished_at TIMESTAMP,
            database_path VARCHAR,
            root_path VARCHAR,
            duckdb_version VARCHAR,
            total_discovered_files BIGINT,
            total_imported_rows BIGINT,
            status VARCHAR
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS _import_audit (
            target_table VARCHAR,
            snapshot_date DATE,
            source_directory VARCHAR,
            file_key VARCHAR,
            file_count BIGINT,
            imported_row_count BIGINT,
            import_started_at TIMESTAMP,
            import_finished_at TIMESTAMP
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS _source_files (
            target_table VARCHAR,
            snapshot_date DATE,
            source_directory VARCHAR,
            file_key VARCHAR,
            source_file VARCHAR,
            file_size_bytes BIGINT
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS _schema_audit (
            target_table VARCHAR,
            column_name VARCHAR,
            column_type VARCHAR,
            expected_column BOOLEAN,
            audit_note VARCHAR
        )
        """
    )


def register_source_files(
    connection: duckdb.DuckDBPyConnection,
    files: list[DiscoveredFile],
) -> None:
    rows = [
        (
            item.target_table,
            item.snapshot_date,
            item.source_directory,
            item.file_key,
            normalize_path(item.path),
            item.path.stat().st_size,
        )
        for item in files
    ]

    connection.executemany(
        """
        INSERT INTO _source_files (
            target_table,
            snapshot_date,
            source_directory,
            file_key,
            source_file,
            file_size_bytes
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def import_batch(
    connection: duckdb.DuckDBPyConnection,
    target_table: str,
    snapshot_date: date,
    source_directory: str,
    file_key: str,
    files: list[DiscoveredFile],
    table_already_exists: bool,
) -> int:
    """
    Import one batch.

    DuckDB's filename=true adds a column named filename. We rename it to
    source_file while retaining every original Parquet column.
    """
    file_paths = [normalize_path(item.path) for item in files]
    table_sql = quote_identifier(target_table)

    started_at = datetime.now()

    # Each batch belongs to one target table and one snapshot date.
    select_sql = """
        SELECT
            * EXCLUDE (filename),
            CAST(? AS DATE) AS snapshot_date,
            filename AS source_file
        FROM read_parquet(
            ?,
            union_by_name = true,
            filename = true
        )
    """

    connection.execute("BEGIN TRANSACTION")

    try:
        if not table_already_exists:
            sql = f"""
                CREATE TABLE {table_sql} AS
                {select_sql}
            """
            connection.execute(sql, [snapshot_date, file_paths])
        else:
            # BY NAME protects against differences in physical column order.
            sql = f"""
                INSERT INTO {table_sql} BY NAME
                {select_sql}
            """
            connection.execute(sql, [snapshot_date, file_paths])

        # Count imported rows for this exact batch by source filename.
        # Querying source_file is safer than assuming each Parquet has rows.
        imported_rows = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {table_sql}
            WHERE snapshot_date = ?
              AND source_file IN (
                  SELECT UNNEST(?::VARCHAR[])
              )
            """,
            [snapshot_date, file_paths],
        ).fetchone()[0]

        finished_at = datetime.now()

        connection.execute(
            """
            INSERT INTO _import_audit (
                target_table,
                snapshot_date,
                source_directory,
                file_key,
                file_count,
                imported_row_count,
                import_started_at,
                import_finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                target_table,
                snapshot_date,
                source_directory,
                file_key,
                len(files),
                imported_rows,
                started_at,
                finished_at,
            ],
        )

        connection.execute("COMMIT")
        return int(imported_rows)

    except Exception:
        connection.execute("ROLLBACK")
        raise


def audit_schema(
    connection: duckdb.DuckDBPyConnection,
    tables_created: set[str],
) -> list[str]:
    warnings: list[str] = []

    connection.execute("DELETE FROM _schema_audit")

    for table_name in sorted(tables_created):
        rows = connection.execute(
            f"DESCRIBE {quote_identifier(table_name)}"
        ).fetchall()

        actual_columns = {
            str(row[0]).lower(): str(row[1])
            for row in rows
        }

        expected = EXPECTED_COLUMNS.get(table_name, set())
        expected_with_metadata = expected | {"snapshot_date", "source_file"}

        missing_columns = expected - set(actual_columns)
        extra_columns = set(actual_columns) - expected_with_metadata

        for column_name, column_type in actual_columns.items():
            is_expected = column_name in expected_with_metadata

            if column_name in {"snapshot_date", "source_file"}:
                note = "Added by build script"
            elif is_expected:
                note = "Expected source column"
            else:
                note = "Unexpected source column; preserved without deletion"

            connection.execute(
                """
                INSERT INTO _schema_audit (
                    target_table,
                    column_name,
                    column_type,
                    expected_column,
                    audit_note
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    table_name,
                    column_name,
                    column_type,
                    is_expected,
                    note,
                ],
            )

        if missing_columns:
            warnings.append(
                f"{table_name}: missing expected columns: "
                + ", ".join(sorted(missing_columns))
            )

        if extra_columns:
            warnings.append(
                f"{table_name}: unexpected columns were preserved: "
                + ", ".join(sorted(extra_columns))
            )

    return warnings


def create_helper_views(
    connection: duckdb.DuckDBPyConnection,
    tables_created: set[str],
) -> None:
    """
    Create useful views without changing source tables.
    """

    if "match_event" in tables_created:
        connection.execute(
            """
            CREATE OR REPLACE VIEW v_match_event_readable AS
            SELECT
                *,
                CASE
                    WHEN start_datetime IS NULL THEN NULL
                    ELSE to_timestamp(start_datetime)
                END AS start_datetime_utc
            FROM match_event
            """
        )

    # A compact match overview. One-to-many tables such as odds, statistics,
    # power and point-by-point are intentionally not joined here because that
    # would multiply rows.
    required = {
        "match_event",
        "match_home_team",
        "match_away_team",
        "match_tournament",
    }

    if required.issubset(tables_created):
        connection.execute(
            """
            CREATE OR REPLACE VIEW v_match_overview AS
            SELECT
                e.snapshot_date,
                e.match_id,
                e.match_slug,
                e.winner_code,
                e.first_to_serve,
                e.start_datetime,
                to_timestamp(e.start_datetime) AS start_datetime_utc,

                h.player_id AS home_player_id,
                h.name AS home_player_name,
                h.country AS home_player_country,
                h.current_rank AS home_player_rank,

                a.player_id AS away_player_id,
                a.name AS away_player_name,
                a.country AS away_player_country,
                a.current_rank AS away_player_rank,

                t.tournament_id,
                t.tournament_name,
                t.tournament_category_name,
                t.ground_type,

                e.source_file AS event_source_file
            FROM match_event AS e

            LEFT JOIN match_home_team AS h
                ON e.match_id = h.match_id
               AND e.snapshot_date = h.snapshot_date

            LEFT JOIN match_away_team AS a
                ON e.match_id = a.match_id
               AND e.snapshot_date = a.snapshot_date

            LEFT JOIN match_tournament AS t
                ON e.match_id = t.match_id
               AND e.snapshot_date = t.snapshot_date
            """
        )


def write_problem_report(
    report_path: Path,
    unclassified: list[Path],
    missing_date: list[Path],
    schema_warnings: list[str],
) -> None:
    report = {
        "unclassified_parquet_count": len(unclassified),
        "parquet_without_valid_date_count": len(missing_date),
        "unclassified_parquet_files": [
            normalize_path(path) for path in unclassified
        ],
        "parquet_files_without_valid_date": [
            normalize_path(path) for path in missing_date
        ],
        "schema_warnings": schema_warnings,
    }

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_discovery_summary(files: list[DiscoveredFile]) -> None:
    counts_by_table = Counter(item.target_table for item in files)
    dates = sorted({item.snapshot_date for item in files})

    print("\nDiscovery summary")
    print("=" * 72)
    print(f"Recognized Parquet files: {len(files):,}")

    if dates:
        print(f"First snapshot date:       {dates[0]}")
        print(f"Last snapshot date:        {dates[-1]}")
        print(f"Distinct snapshot dates:   {len(dates):,}")

    print("\nFiles by target table:")

    for table_name in sorted(counts_by_table):
        print(f"  {table_name:<28} {counts_by_table[table_name]:>10,}")

    print("=" * 72)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a DuckDB database from tennis Parquet snapshots."
    )

    parser.add_argument(
        "--root",
        type=Path,
        default=Path(".."),
        help=(
            "Root directory containing date folders. "
            "Default: current directory."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_DATABASE_NAME),
        help=f"Output DuckDB file. Default: {DEFAULT_DATABASE_NAME}",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Maximum Parquet files read in each batch. "
            f"Default: {DEFAULT_BATCH_SIZE}"
        ),
    )

    parser.add_argument(
        "--memory-limit",
        default=DEFAULT_MEMORY_LIMIT,
        help=f"DuckDB memory limit. Default: {DEFAULT_MEMORY_LIMIT}",
    )

    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_THREADS,
        help=f"Number of DuckDB threads. Default: {DEFAULT_THREADS}",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the existing output database if it exists.",
    )

    parser.add_argument(
        "--allow-unclassified",
        action="store_true",
        help=(
            "Continue even when Parquet files in known source directories "
            "cannot be classified. By default the script stops to protect "
            "against accidentally skipping data."
        ),
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main build workflow
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_arguments()

    root = args.root.resolve()
    output = args.output.resolve()
    temp_directory = output.parent / DEFAULT_TEMP_DIRECTORY
    report_path = output.with_name(output.stem + "_build_report.json")

    if args.batch_size <= 0:
        print("ERROR: --batch-size must be greater than zero.", file=sys.stderr)
        return 1

    if args.threads <= 0:
        print("ERROR: --threads must be greater than zero.", file=sys.stderr)
        return 1

    if not root.exists() or not root.is_dir():
        print(f"ERROR: root directory does not exist:\n  {root}", file=sys.stderr)
        return 1

    if output.exists():
        if not args.overwrite:
            print(
                "ERROR: output database already exists:\n"
                f"  {output}\n\n"
                "Nothing was changed. Use --overwrite if you really want "
                "to rebuild it.",
                file=sys.stderr,
            )
            return 1

        print(f"Removing existing database:\n  {output}")
        output.unlink()

        # DuckDB may leave these files after an interrupted build.
        for suffix in (".wal", ".tmp"):
            sidecar = Path(str(output) + suffix)

            if sidecar.exists():
                sidecar.unlink()

    output.parent.mkdir(parents=True, exist_ok=True)

    build_started_at = datetime.now()
    wall_start = time.perf_counter()

    discovered, unclassified, missing_date = discover_files(root)

    print_discovery_summary(discovered)

    if missing_date:
        print(
            f"\nWARNING: {len(missing_date):,} Parquet files were found inside "
            "known source directories, but no valid date folder could be "
            "identified."
        )

    if unclassified:
        print(
            f"\nWARNING: {len(unclassified):,} Parquet files were found inside "
            "known source directories but could not be classified."
        )

        # Default behavior is deliberately strict because user said no data
        # may be omitted.
        if not args.allow_unclassified:
            write_problem_report(
                report_path,
                unclassified,
                missing_date,
                schema_warnings=[],
            )

            print(
                "\nBuild stopped before creating the database, because "
                "unclassified files might otherwise be skipped.\n"
                f"Inspect this report:\n  {report_path}\n\n"
                "If those files are intentionally irrelevant, rerun with:\n"
                "  --allow-unclassified"
            )
            return 2

    if not discovered:
        write_problem_report(
            report_path,
            unclassified,
            missing_date,
            schema_warnings=[],
        )

        print(
            "\nERROR: no classifiable Parquet files were found.\n"
            "Check --root, date-folder names, and Parquet filenames.\n"
            f"Report:\n  {report_path}",
            file=sys.stderr,
        )
        return 1

    # Group by table and date. This lets us add snapshot_date accurately
    # without loading a Python DataFrame.
    grouped: dict[tuple[str, date, str, str], list[DiscoveredFile]] = defaultdict(list)

    for item in discovered:
        key = (
            item.target_table,
            item.snapshot_date,
            item.source_directory,
            item.file_key,
        )
        grouped[key].append(item)

    connection: duckdb.DuckDBPyConnection | None = None
    total_imported_rows = 0
    tables_created: set[str] = set()

    try:
        connection = initialize_connection(
            database_path=output,
            memory_limit=args.memory_limit,
            threads=args.threads,
            temp_directory=temp_directory,
        )

        create_metadata_tables(connection)
        register_source_files(connection, discovered)

        total_groups = len(grouped)
        completed_groups = 0

        print("\nStarting import")
        print("=" * 72)

        for group_key in sorted(grouped):
            target_table, snapshot_date, source_directory, file_key = group_key
            group_files = grouped[group_key]

            group_row_count = 0
            batch_count = (
                len(group_files) + args.batch_size - 1
            ) // args.batch_size

            for batch_number, batch in enumerate(
                chunked(group_files, args.batch_size),
                start=1,
            ):
                print(
                    f"[{completed_groups + 1}/{total_groups}] "
                    f"{target_table} | {snapshot_date} | "
                    f"batch {batch_number}/{batch_count} | "
                    f"{len(batch):,} files",
                    flush=True,
                )

                imported_rows = import_batch(
                    connection=connection,
                    target_table=target_table,
                    snapshot_date=snapshot_date,
                    source_directory=source_directory,
                    file_key=file_key,
                    files=batch,
                    table_already_exists=target_table in tables_created,
                )

                tables_created.add(target_table)
                group_row_count += imported_rows
                total_imported_rows += imported_rows

            completed_groups += 1

            print(
                f"    Imported rows for group: {group_row_count:,}",
                flush=True,
            )

        print("=" * 72)

        schema_warnings = audit_schema(connection, tables_created)
        create_helper_views(connection, tables_created)

        # Force DuckDB to persist its current state.
        connection.execute("CHECKPOINT")

        build_finished_at = datetime.now()

        connection.execute(
            """
            INSERT INTO _build_info (
                build_started_at,
                build_finished_at,
                database_path,
                root_path,
                duckdb_version,
                total_discovered_files,
                total_imported_rows,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                build_started_at,
                build_finished_at,
                normalize_path(output),
                normalize_path(root),
                duckdb.__version__,
                len(discovered),
                total_imported_rows,
                "success",
            ],
        )

        connection.execute("CHECKPOINT")

        write_problem_report(
            report_path,
            unclassified,
            missing_date,
            schema_warnings,
        )

        elapsed = time.perf_counter() - wall_start
        database_size = output.stat().st_size

        print("\nBuild completed successfully 🎾")
        print("=" * 72)
        print(f"Database:             {output}")
        print(f"Build report:         {report_path}")
        print(f"Imported files:       {len(discovered):,}")
        print(f"Imported rows:        {total_imported_rows:,}")
        print(f"Created data tables:  {len(tables_created):,}")
        print(f"Database size:        {database_size / (1024 ** 3):.2f} GB")
        print(f"Elapsed time:         {elapsed / 60:.2f} minutes")

        if schema_warnings:
            print("\nSchema warnings:")

            for warning in schema_warnings:
                print(f"  - {warning}")

            print(
                "\nNo unexpected columns were deleted. "
                "See _schema_audit and the JSON report."
            )

        if missing_date:
            print(
                f"\nWARNING: {len(missing_date):,} files without a recognized "
                "snapshot date were not imported. See the JSON report."
            )

        if unclassified:
            print(
                f"\nWARNING: {len(unclassified):,} unclassified files were not "
                "imported because --allow-unclassified was used. "
                "See the JSON report."
            )

        print("=" * 72)

        return 0

    except KeyboardInterrupt:
        print(
            "\nBuild interrupted by user. The database may be incomplete.\n"
            "Rerun with --overwrite to rebuild it cleanly.",
            file=sys.stderr,
        )
        return 130

    except Exception as exc:
        print("\nBUILD FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "\nThe original Parquet files were not modified.\n"
            "Fix the reported issue and rerun with --overwrite.",
            file=sys.stderr,
        )
        return 1

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
