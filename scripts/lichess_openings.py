#!/usr/bin/env python3
"""Poll Lichess TV channels and group live games by opening."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Iterable

import requests

LICHESS_TV_URL = "https://lichess.org/api/tv/channels"
LICHESS_GAME_EXPORT = "https://lichess.org/game/export/{game_id}"


@dataclass(frozen=True)
class LiveGame:
    game_id: str
    channel: str
    opening_name: str
    eco: str
    white: str
    black: str
    moves: str


class LichessClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "ChessOpeningsLive/0.1"})

    def fetch_tv_channels(self) -> list[dict]:
        response = self.session.get(LICHESS_TV_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("channels", [])

    def fetch_game(self, game_id: str) -> dict:
        response = self.session.get(
            LICHESS_GAME_EXPORT.format(game_id=game_id),
            params={
                "moves": "true",
                "opening": "true",
                "clocks": "false",
                "evals": "false",
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


def build_live_game(channel: dict, game_data: dict) -> LiveGame:
    opening = game_data.get("opening") or {}
    players = game_data.get("players") or {}
    return LiveGame(
        game_id=game_data.get("id", ""),
        channel=channel.get("name", ""),
        opening_name=opening.get("name", "Unknown"),
        eco=opening.get("eco", ""),
        white=players.get("white", {}).get("user", {}).get("name", "Unknown"),
        black=players.get("black", {}).get("user", {}).get("name", "Unknown"),
        moves=game_data.get("moves", ""),
    )


def fetch_openings(client: LichessClient, limit: int | None) -> Iterable[LiveGame]:
    channels = client.fetch_tv_channels()
    if limit is not None:
        channels = channels[:limit]
    for channel in channels:
        game_id = channel.get("gameId")
        if not game_id:
            continue
        game_data = client.fetch_game(game_id)
        yield build_live_game(channel, game_data)


def format_opening_key(game: LiveGame) -> str:
    if game.eco:
        return f"{game.eco} {game.opening_name}"
    return game.opening_name


def render_grouped(games: Iterable[LiveGame]) -> str:
    grouped: dict[str, list[LiveGame]] = {}
    for game in games:
        grouped.setdefault(format_opening_key(game), []).append(game)

    lines = []
    for opening, opening_games in sorted(grouped.items()):
        lines.append(f"\n{opening} ({len(opening_games)} games)")
        for game in opening_games:
            url = f"https://lichess.org/{game.game_id}"
            players = f"{game.white} vs {game.black}"
            lines.append(f"  - {players} [{game.channel}] {url}")
    return "\n".join(lines).lstrip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll Lichess TV channels and group live games by opening.",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=0,
        help="Seconds between polls (0 for single run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of TV channels to inspect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of formatted text",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    client = LichessClient()

    while True:
        games = list(fetch_openings(client, args.limit))
        if args.json:
            payload = [game.__dict__ for game in games]
            print(json.dumps(payload, indent=2))
        else:
            print(render_grouped(games))

        if args.poll_interval <= 0:
            break
        time.sleep(args.poll_interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
