#!/usr/bin/env python3
"""Export one season (≈ one calendar month) of guild standings to a CSV.

This runs wherever the bot runs, because it reuses the bot's own database
connection from database.py (same .env, same MySQL access). The resulting CSV
is what the end-of-season leaderboard image generator reads.

Usage:
    python export_season.py                  # latest month present in the DB
    python export_season.py --month 2025-10  # a specific season
    python export_season.py --month 2025-10 --out season_oct.csv

Assumptions about the `submissions` table (all already used elsewhere in
database.py): it has columns date, result, points_scored, opponent_scored,
total_points, league, guild_id. `result` is expected to be 'Win'/'Loss'/'Draw';
if it's ever empty the script falls back to comparing points_scored vs
opponent_scored.
"""
import argparse
import asyncio
import csv
from datetime import date

import database  # reuses connect_db(), pool, close_db() and .env loading


def month_bounds(year: int, month: int):
    """Return [first day of month, first day of next month)."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


async def fetch_rows(start: date, end: date):
    async with database.pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT g.id, g.guild_name, g.server_number,
                       s.date, s.result, s.points_scored, s.opponent_scored,
                       s.total_points, s.league
                FROM guilds g
                JOIN submissions s ON s.guild_id = g.id
                WHERE s.date >= %s AND s.date < %s
                ORDER BY g.id, s.date
                """,
                (start, end),
            )
            return await cursor.fetchall()


def classify(result, scored, opp):
    """Normalise a war result to Win/Loss/Draw, falling back to the scores."""
    if result:
        r = str(result).strip().lower()
        if r.startswith("w"):
            return "Win"
        if r.startswith("l"):
            return "Loss"
        if r.startswith("d"):
            return "Draw"
    try:
        if scored > opp:
            return "Win"
        if scored < opp:
            return "Loss"
        return "Draw"
    except TypeError:
        return None


def aggregate(rows):
    """Roll raw submissions up into one record per guild for the season."""
    guilds = {}
    for gid, name, server, d, result, scored, opp, total_points, league in rows:
        g = guilds.setdefault(
            gid,
            {
                "name": name,
                "server": server,
                "W": 0,
                "D": 0,
                "L": 0,
                "results": [],
                "dates": [],
                "points": 0,
                "league": None,
                "latest": None,
            },
        )
        outcome = classify(result, scored, opp)
        if outcome == "Win":
            g["W"] += 1
        elif outcome == "Loss":
            g["L"] += 1
        elif outcome == "Draw":
            g["D"] += 1
        if outcome:
            g["results"].append(outcome)
        g["dates"].append(str(d))
        # the latest submission of the season carries the standing/league
        if g["latest"] is None or d >= g["latest"]:
            g["latest"] = d
            if total_points is not None:
                g["points"] = int(total_points)
            g["league"] = league
    return guilds


async def standings_for(year: int, month: int):
    """Aggregated guilds + a {guild_id: rank} map for one month."""
    start, end = month_bounds(year, month)
    guilds = aggregate(await fetch_rows(start, end))
    ordered = sorted(guilds.items(), key=lambda kv: kv[1]["points"], reverse=True)
    ranks = {gid: i + 1 for i, (gid, _) in enumerate(ordered)}
    return guilds, ordered, ranks


async def latest_month():
    async with database.pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT MAX(date) FROM submissions")
            row = await cursor.fetchone()
    return row[0] if row else None


async def main():
    ap = argparse.ArgumentParser(description="Export a season's standings to CSV.")
    ap.add_argument("--month", help="Season month as YYYY-MM (default: latest in DB)")
    ap.add_argument("--out", help="Output CSV path (default: season_YYYY-MM.csv)")
    args = ap.parse_args()

    await database.connect_db()
    try:
        if args.month:
            year, month = (int(x) for x in args.month.split("-"))
        else:
            latest = await latest_month()
            if latest is None:
                print("No submissions found in the database.")
                return
            year, month = latest.year, latest.month

        guilds, ordered, ranks = await standings_for(year, month)
        if not ordered:
            print(f"No submissions found for {year:04d}-{month:02d}.")
            return

        # previous month's ranks, for the up/down movement arrows
        prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
        try:
            _, _, prev_ranks = await standings_for(prev_y, prev_m)
        except Exception:
            prev_ranks = {}

        out = args.out or f"season_{year:04d}-{month:02d}.csv"
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                [
                    "Rank",
                    "Rank Movement",
                    "Guild Name",
                    "Server",
                    "Wins",
                    "Draws",
                    "Losses",
                    "Points",
                    "League",
                    "Latest Submission Date",
                    "All Results",
                ]
            )
            for rank, (gid, g) in enumerate(ordered, start=1):
                prev = prev_ranks.get(gid)
                if prev is None:
                    movement = "new"
                elif prev > rank:
                    movement = "up"
                elif prev < rank:
                    movement = "down"
                else:
                    movement = "same"
                writer.writerow(
                    [
                        rank,
                        movement,
                        g["name"],
                        f"S{g['server']}",
                        g["W"],
                        g["D"],
                        g["L"],
                        g["points"],
                        g["league"] or "",
                        str(g["latest"]) if g["latest"] else "",
                        ", ".join(g["results"]),
                    ]
                )
        print(f"Wrote {out} — {len(ordered)} guilds for season {year:04d}-{month:02d}")
    finally:
        await database.close_db()


if __name__ == "__main__":
    asyncio.run(main())
