#!/usr/bin/env python3
"""Poll Lichess TV channels and group live games by opening."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from http import HTTPStatus
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LICHESS_TV_URL = "https://lichess.org/api/tv/channels"
LICHESS_BROADCASTS_URL = "https://lichess.org/api/broadcast"
LICHESS_BROADCAST_ROUND_URL = "https://lichess.org/api/broadcast/round/{round_id}"
LICHESS_GAME_EXPORT = "https://lichess.org/game/export/{game_id}"
LICHESS_EXPORT_IDS_URL = "https://lichess.org/api/games/export/_ids"
LICHESS_EXPLORER_URL = "https://explorer.lichess.ovh/lichess"
DEFAULT_PORT = 8000
DEFAULT_STATS_FILE = "opening_stats.json"

# Maps opening names to UCI move sequences for the Lichess Opening Explorer API.
OPENING_MOVES: dict[str, str] = {
    "Alekhine's Defense":     "e2e4,g8f6",
    "Benoni Defense":         "d2d4,g8f6,c2c4,c7c5,d4d5",
    "Bird's Opening":         "f2f4",
    "Budapest Gambit":        "d2d4,g8f6,c2c4,e7e5",
    "Caro-Kann Defense":      "e2e4,c7c6",
    "Catalan Opening":        "d2d4,g8f6,c2c4,e7e6,g2g3",
    "Dutch Defense":          "d2d4,f7f5",
    "English Opening":        "c2c4",
    "Four Knights Game":      "e2e4,e7e5,g1f3,b8c6,b1c3,g8f6",
    "French Defense":         "e2e4,e7e6",
    "Grünfeld Defense":       "d2d4,g8f6,c2c4,g7g6,b1c3,d7d5",
    "Italian Game":           "e2e4,e7e5,g1f3,b8c6,f1c4",
    "King's Gambit":          "e2e4,e7e5,f2f4",
    "King's Indian Defense":  "d2d4,g8f6,c2c4,g7g6,b1c3,f8g7",
    "London System":          "d2d4,d7d5,g1f3,g8f6,c1f4",
    "Nimzo-Indian Defense":   "d2d4,g8f6,c2c4,e7e6,b1c3,f8b4",
    "Petrov's Defense":       "e2e4,e7e5,g1f3,g8f6",
    "Pirc Defense":           "e2e4,d7d6,d2d4,g8f6,b1c3,g7g6",
    "Queen's Gambit":         "d2d4,d7d5,c2c4",
    "Queen's Indian Defense": "d2d4,g8f6,c2c4,e7e6,g1f3,b7b6",
    "Réti Opening":           "g1f3",
    "Ruy Lopez":              "e2e4,e7e5,g1f3,b8c6,f1b5",
    "Scandinavian Defense":   "e2e4,d7d5",
    "Scotch Game":            "e2e4,e7e5,g1f3,b8c6,d2d4",
    "Semi-Slav Defense":      "d2d4,d7d5,c2c4,c7c6,b1c3,g8f6,g1f3,e7e6",
    "Sicilian Defense":       "e2e4,c7c5",
    "Sicilian Dragon":        "e2e4,c7c5,g1f3,d7d6,d2d4,c5d4,f3d4,g8f6,b1c3,g7g6",
    "Sicilian Najdorf":       "e2e4,c7c5,g1f3,d7d6,d2d4,c5d4,f3d4,g8f6,b1c3,a7a6",
    "Sicilian Scheveningen":  "e2e4,c7c5,g1f3,d7d6,d2d4,c5d4,f3d4,g8f6,b1c3,e7e6",
    "Slav Defense":           "d2d4,d7d5,c2c4,c7c6",
    "Vienna Game":            "e2e4,e7e5,b1c3",
}


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
    def __init__(self, *, debug: bool = False) -> None:
        self.user_agent = "ChessOpeningsLive/0.1"
        self.debug = debug

    def _fetch_text(self, url: str, params: dict[str, str] | None = None) -> str:
        if params:
            query = "&".join(f"{key}={value}" for key, value in params.items())
            url = f"{url}?{query}"
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"Failed to fetch {url}: {error}") from error

    def _fetch_json(self, url: str, params: dict[str, str] | None = None) -> dict:
        body = self._fetch_text(url, params=params)
        return json.loads(body)

    def _fetch_ndjson(self, url: str) -> list[dict]:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/x-ndjson",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"Failed to fetch {url}: {error}") from error
        if self.debug:
            print("DEBUG: Raw broadcast payload:", file=sys.stderr)
            print(body, file=sys.stderr)
        items = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
        return items

    def _fetch_post_ndjson(self, url: str, body: str) -> list[dict]:
        """POST *body* and parse the NDJSON response."""
        request = Request(
            url,
            data=body.encode("utf-8"),
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "text/plain",
                "Accept": "application/x-ndjson",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"Failed to POST {url}: {error}") from error
        items = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                items.append(json.loads(line))
        return items

    def fetch_tv_channels(self) -> list[dict]:
        raw_body = self._fetch_text(LICHESS_TV_URL)
        if self.debug:
            print("DEBUG: Raw TV payload:", file=sys.stderr)
            print(raw_body, file=sys.stderr)
        data = json.loads(raw_body)
        if "channels" not in data and isinstance(data, dict):
            return [
                {**payload, "name": payload.get("name", name)}
                for name, payload in data.items()
                if isinstance(payload, dict)
            ]
        channels = data.get("channels", [])
        if isinstance(channels, dict):
            normalized = []
            for name, payload in channels.items():
                if isinstance(payload, dict):
                    normalized.append({**payload, "name": payload.get("name", name)})
            return normalized
        if isinstance(channels, list):
            return channels
        return []

    def fetch_broadcasts(self) -> list[dict]:
        return self._fetch_ndjson(LICHESS_BROADCASTS_URL)

    def fetch_broadcast_round(self, round_id: str) -> dict:
        return self._fetch_json(LICHESS_BROADCAST_ROUND_URL.format(round_id=round_id))

    def fetch_game(self, game_id: str) -> dict:
        return self._fetch_json(
            LICHESS_GAME_EXPORT.format(game_id=game_id),
            params={
                "moves": "true",
                "opening": "true",
                "clocks": "false",
                "evals": "false",
            },
        )


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


def extract_game_id(channel: dict) -> str | None:
    if "gameId" in channel:
        return channel.get("gameId")
    game = channel.get("game")
    if isinstance(game, dict):
        return game.get("id")
    return None


def extract_game_id_from_url(url: str) -> str | None:
    if not url:
        return None
    trimmed = url.rstrip("/")
    if not trimmed:
        return None
    return trimmed.split("/")[-1] or None


def fetch_openings_from_tv(client: LichessClient, limit: int | None) -> list[LiveGame]:
    channels = client.fetch_tv_channels()
    if limit is not None:
        channels = channels[:limit]
    games: list[LiveGame] = []
    for channel in channels:
        game_id = extract_game_id(channel)
        if not game_id:
            continue
        game_data = client.fetch_game(game_id)
        games.append(build_live_game(channel, game_data))
    return games


def fetch_broadcast_rounds(broadcasts: list[dict]) -> list[dict]:
    now_ms = int(time.time() * 1000)
    rounds: list[dict] = []
    for item in broadcasts:
        tour = item.get("tour") or {}
        default_round = tour.get("defaultRoundId")
        if default_round:
            rounds.append({"id": str(default_round), "url": None})
        for round_info in item.get("rounds", []) or []:
            if not isinstance(round_info, dict):
                continue
            if round_info.get("finished") is True:
                continue
            starts_at = round_info.get("startsAt")
            if isinstance(starts_at, int) and starts_at > now_ms:
                continue
            round_id = round_info.get("id")
            if round_id:
                rounds.append(
                    {
                        "id": str(round_id),
                        "url": round_info.get("url"),
                    }
                )
    seen: set[str] = set()
    deduped: list[dict] = []
    for round_info in rounds:
        round_id = round_info["id"]
        if round_id in seen:
            continue
        seen.add(round_id)
        deduped.append(round_info)
    return deduped


def extract_round_game_ids(round_payload: dict) -> list[str]:
    game_ids: list[str] = []
    games = round_payload.get("games") or round_payload.get("pairings") or []
    if isinstance(games, dict):
        games = list(games.values())
    if isinstance(games, list):
        for game in games:
            if not isinstance(game, dict):
                continue
            game_id = (
                game.get("id")
                or game.get("gameId")
                or game.get("lichessId")
                or game.get("game", {}).get("id")
                or extract_game_id_from_url(game.get("url", ""))
            )
            if game_id:
                game_ids.append(str(game_id))
    return game_ids


def fetch_broadcast_round_payload(client: LichessClient, round_info: dict) -> dict:
    round_id = round_info["id"]
    round_url = round_info.get("url")
    if round_url:
        api_url = round_url.replace("https://lichess.org", "https://lichess.org/api")
        if client.debug:
            print(f"DEBUG: Fetching broadcast round via {api_url}", file=sys.stderr)
        return client._fetch_json(api_url)
    return client.fetch_broadcast_round(round_id)


def fetch_openings_from_broadcast(
    client: LichessClient, limit: int | None
) -> list[LiveGame]:
    broadcasts = client.fetch_broadcasts()
    round_infos = fetch_broadcast_rounds(broadcasts)
    if limit is not None:
        round_infos = round_infos[:limit]
    games: list[LiveGame] = []
    for round_info in round_infos:
        round_id = round_info["id"]
        try:
            round_payload = fetch_broadcast_round_payload(client, round_info)
        except RuntimeError as error:
            if "HTTP Error 404" in str(error):
                if client.debug:
                    print(
                        f"DEBUG: Skipping missing broadcast round {round_id}",
                        file=sys.stderr,
                    )
                continue
            raise
        game_ids = extract_round_game_ids(round_payload)
        if client.debug and not game_ids:
            print(
                f"DEBUG: No game IDs found in broadcast round {round_id}",
                file=sys.stderr,
            )
        for game_id in game_ids:
            game_data = client.fetch_game(game_id)
            games.append(build_live_game({"name": "Broadcast"}, game_data))
    return games


def fetch_openings(
    client: LichessClient, limit: int | None, source: str
) -> list[LiveGame]:
    if source == "tv":
        return fetch_openings_from_tv(client, limit)
    if source == "broadcast":
        return fetch_openings_from_broadcast(client, limit)
    if source == "auto":
        games = fetch_openings_from_tv(client, limit)
        if games:
            return games
        return fetch_openings_from_broadcast(client, limit)
    raise ValueError(f"Unknown source: {source}")


def resolve_opening_moves(name: str) -> tuple[str, str] | None:
    """Return (canonical_name, uci_moves) for *name*, or None if not found.

    Tries an exact match first, then a case-insensitive substring match.
    """
    if name in OPENING_MOVES:
        return name, OPENING_MOVES[name]
    lower = name.lower()
    for canonical, moves in OPENING_MOVES.items():
        if lower in canonical.lower():
            return canonical, moves
    return None


def search_live_games_by_opening(client: LichessClient, opening_name: str) -> list[dict]:
    """Return live and recent games for *opening_name*, sorted by avg rating.

    Uses the Lichess Opening Explorer to retrieve recent game IDs, then
    bulk-fetches their details. Live games (status "started") are sorted
    first; within each group games are ordered by average rating descending.
    """
    resolved = resolve_opening_moves(opening_name)
    if resolved is None:
        return []
    canonical_name, moves = resolved

    # Query the explorer for recent games of this opening.
    # The ratings filter may require a Lichess OAuth token; fall back to an
    # unfiltered query if the API returns 401.
    now = time.strftime("%Y-%m")
    explorer_base = (
        f"{LICHESS_EXPLORER_URL}?play={moves}"
        f"&recentGames=8&topGames=0"
        f"&speeds=blitz,rapid,classical"
        f"&since={now}"
    )
    try:
        explorer_data = client._fetch_json(
            f"{explorer_base}&ratings=1600,1800,2000,2200,2500"
        )
    except RuntimeError as exc:
        cause = exc.__cause__
        if not (isinstance(cause, HTTPError) and cause.code == 401):
            raise
        explorer_data = client._fetch_json(explorer_base)
    recent_games = explorer_data.get("recentGames") or []
    game_ids = [g["id"] for g in recent_games if g.get("id")]
    if not game_ids:
        return []

    # Bulk-fetch game details to get status and ratings.
    games = client._fetch_post_ndjson(LICHESS_EXPORT_IDS_URL, ",".join(game_ids))

    results: list[dict] = []
    for game in games:
        players = game.get("players") or {}
        white = players.get("white") or {}
        black = players.get("black") or {}
        white_rating: int = white.get("rating") or 0
        black_rating: int = black.get("rating") or 0
        avg_rating = (
            (white_rating + black_rating) // 2
            if white_rating and black_rating
            else white_rating or black_rating
        )
        opening_data = game.get("opening") or {}
        game_id = game.get("id") or ""
        results.append(
            {
                "id": game_id,
                "url": f"https://lichess.org/{game_id}",
                "white": (white.get("user") or {}).get("name") or "Anonymous",
                "whiteRating": white_rating,
                "black": (black.get("user") or {}).get("name") or "Anonymous",
                "blackRating": black_rating,
                "avgRating": avg_rating,
                "isLive": game.get("status") == "started",
                "status": game.get("status") or "",
                "opening": opening_data.get("name") or canonical_name,
                "eco": opening_data.get("eco") or "",
                "createdAt": game.get("createdAt") or 0,
            }
        )

    # Live games first, then sort by avg rating descending within each group.
    results.sort(key=lambda g: (not g["isLive"], -g["avgRating"]))
    return results


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


def build_openings_payload(games: Iterable[LiveGame]) -> list[dict]:
    grouped: dict[str, list[LiveGame]] = {}
    for game in games:
        grouped.setdefault(format_opening_key(game), []).append(game)

    payload = []
    for opening, opening_games in sorted(
        grouped.items(),
        key=lambda item: (
            item[0].lower().startswith("unknown"),
            -len(item[1]),
            item[0].lower(),
        ),
    ):
        payload.append(
            {
                "opening": opening,
                "count": len(opening_games),
                "games": [
                    {
                        "url": f"https://lichess.org/{game.game_id}",
                        "players": f"{game.white} vs {game.black}",
                        "channel": game.channel,
                        "moves": game.moves,
                    }
                    for game in opening_games
                ],
            }
        )
    return payload


def load_stats(stats_path: Path) -> dict:
    if not stats_path.exists():
        return {"updated_at": None, "openings": {}}
    try:
        return json.loads(stats_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"updated_at": None, "openings": {}}


def update_stats(stats: dict, games: Iterable[LiveGame]) -> dict:
    openings = stats.setdefault("openings", {})
    for game in games:
        key = format_opening_key(game)
        openings[key] = openings.get(key, 0) + 1
    stats["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return stats


def save_stats(stats_path: Path, stats: dict) -> None:
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def render_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Chess Openings Live</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f4f6fb;
        --card: #ffffff;
        --text: #1b1f2a;
        --muted: #5f6b85;
        --accent: #3558d6;
        --accent-soft: #eef2ff;
        --border: #e3e8f4;
        --shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
      }
      * { box-sizing: border-box; }
      body { font-family: "Inter", "Segoe UI", sans-serif; margin: 0; background: var(--bg); color: var(--text); }
      .page { max-width: 960px; margin: 0 auto; padding: 32px 24px 56px; }
      header { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }
      h1 { margin: 0; font-size: 2rem; }
      .meta { color: var(--muted); margin: 0; }
      .controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 20px 0; }
      .controls input { flex: 1 1 280px; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border); background: #fff; }
      .stats { display: flex; gap: 12px; flex-wrap: wrap; }
      .badge { background: var(--accent-soft); color: var(--accent); padding: 6px 10px; border-radius: 999px; font-size: 0.9rem; }
      .link { color: var(--accent); text-decoration: none; font-weight: 600; }
      .link:hover { text-decoration: underline; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
      .opening { background: var(--card); border-radius: 14px; padding: 16px; box-shadow: var(--shadow); border: 1px solid var(--border); }
      .opening h2 { margin: 0 0 8px 0; font-size: 1.05rem; }
      .count { color: var(--muted); font-weight: normal; }
      ul { margin: 0; padding-left: 18px; }
      li { margin-bottom: 8px; }
      a { color: var(--accent); text-decoration: none; }
      a:hover { text-decoration: underline; }
      .channel { color: var(--muted); font-size: 0.9rem; }
      .muted { color: var(--muted); }
      .error { background: #fff2f2; border: 1px solid #f2c0c0; padding: 12px; border-radius: 10px; }
      /* Opening name button in TV grid */
      .opening-name-btn { background: none; border: none; padding: 0; font: inherit; font-size: 1.05rem; font-weight: 600; color: var(--accent); cursor: pointer; text-align: left; }
      .opening-name-btn:hover { text-decoration: underline; }
      /* Search section */
      .search-section { margin-top: 48px; }
      .search-section > h2 { margin: 0 0 4px 0; font-size: 1.3rem; }
      .search-section > .section-meta { color: var(--muted); margin: 0 0 16px 0; font-size: 0.95rem; }
      .search-controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
      .search-controls input { flex: 1 1 260px; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border); background: #fff; font-size: 1rem; }
      .btn { padding: 10px 20px; background: var(--accent); color: #fff; border: none; border-radius: 10px; font-size: 1rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
      .btn:hover { background: #2748c2; }
      .btn:disabled { background: var(--muted); cursor: not-allowed; }
      .sort-toggle { display: flex; gap: 6px; flex-shrink: 0; }
      .sort-btn { padding: 7px 14px; border-radius: 8px; border: 1px solid var(--border); background: #fff; cursor: pointer; font-size: 0.9rem; color: var(--text); }
      .sort-btn.active { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); font-weight: 600; }
      .search-status { color: var(--muted); font-size: 0.9rem; margin: 0 0 12px 0; min-height: 1.3em; }
      .search-status.error { color: #a00; }
      .search-results { display: flex; flex-direction: column; gap: 10px; }
      .game-card { background: var(--card); border-radius: 12px; padding: 14px 16px; box-shadow: var(--shadow); border: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; gap: 12px; }
      .game-card-left { min-width: 0; }
      .game-players { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .opening-label { color: var(--muted); font-size: 0.85rem; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .game-card-right { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
      .rating-badge { background: var(--accent-soft); color: var(--accent); padding: 4px 9px; border-radius: 6px; font-size: 0.85rem; font-weight: 600; white-space: nowrap; }
      .live-badge { background: #fef2f2; color: #b91c1c; padding: 4px 9px; border-radius: 6px; font-size: 0.8rem; font-weight: 700; white-space: nowrap; }
      .recent-badge { background: #f0fdf4; color: #166534; padding: 4px 9px; border-radius: 6px; font-size: 0.8rem; white-space: nowrap; }
    </style>
  </head>
  <body>
    <div class="page">
      <header>
        <h1>Chess Openings Live</h1>
        <p class="meta">Live games grouped by opening (Lichess TV).</p>
      </header>
      <div class="controls">
        <input id="filter" type="text" placeholder="Filter openings or players" />
        <div class="stats">
          <span id="summary" class="badge"></span>
          <span id="status" class="muted"></span>
        </div>
        <a class="link" href="/stats">View opening stats</a>
      </div>
      <div id="openings" class="grid"></div>

      <section class="search-section">
        <h2>Search Live Games by Opening</h2>
        <p class="section-meta">Find Lichess games for any opening, sorted by strongest players. Click an opening name above to pre-fill.</p>
        <div class="search-controls">
          <input id="opening-input" type="text" list="opening-suggestions" placeholder="e.g. King's Gambit, Sicilian Defense…" autocomplete="off" />
          <datalist id="opening-suggestions"></datalist>
          <button id="search-btn" class="btn">Search</button>
          <div class="sort-toggle">
            <button class="sort-btn active" data-sort="rating">Avg Rating ↓</button>
            <button class="sort-btn" data-sort="recent">Most Recent</button>
          </div>
        </div>
        <p id="search-status" class="search-status"></p>
        <div id="search-results" class="search-results"></div>
      </section>
    </div>
    <script>
      // ── TV feed ────────────────────────────────────────────────────────────

      const state = { openings: [], filter: '' };
      const openingsEl = document.getElementById('openings');
      const statusEl = document.getElementById('status');
      const summaryEl = document.getElementById('summary');
      const filterEl = document.getElementById('filter');

      function htmlEscape(str) {
        return String(str)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
      }

      function render() {
        const needle = state.filter.trim().toLowerCase();
        const filtered = state.openings.filter(opening => {
          if (!needle) return true;
          if (opening.opening.toLowerCase().includes(needle)) return true;
          return opening.games.some(game => game.players.toLowerCase().includes(needle));
        });

        if (!filtered.length) {
          openingsEl.innerHTML = '<p class="muted">No live games found.</p>';
        } else {
          openingsEl.innerHTML = filtered.map(opening => {
            const gamesHtml = opening.games.map(game => (
              `<li><a href="${htmlEscape(game.url)}" target="_blank" rel="noopener noreferrer">${htmlEscape(game.players)}</a> <span class="channel">[${htmlEscape(game.channel)}]</span></li>`
            )).join('');
            return `
              <section class="opening">
                <h2><button class="opening-name-btn" data-name="${htmlEscape(opening.opening)}">${htmlEscape(opening.opening)}</button> <span class="count">(${opening.count})</span></h2>
                <ul>${gamesHtml}</ul>
              </section>
            `;
          }).join('');
        }
        const totalGames = filtered.reduce((sum, opening) => sum + opening.count, 0);
        summaryEl.textContent = `${filtered.length} openings · ${totalGames} games`;
      }

      openingsEl.addEventListener('click', event => {
        const btn = event.target.closest('.opening-name-btn');
        if (!btn) return;
        openingInputEl.value = btn.dataset.name;
        document.querySelector('.search-section').scrollIntoView({ behavior: 'smooth' });
        triggerSearch();
      });

      async function refresh() {
        statusEl.textContent = 'Refreshing…';
        statusEl.className = 'muted';
        try {
          const response = await fetch('/api/openings');
          if (!response.ok) {
            const text = await response.text();
            throw new Error(text || `API error (${response.status})`);
          }
          const data = await response.json();
          state.openings = data;
          statusEl.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
          render();
        } catch (error) {
          statusEl.className = 'error';
          statusEl.textContent = error.message;
          openingsEl.innerHTML = '';
          summaryEl.textContent = '';
        }
      }

      filterEl.addEventListener('input', event => {
        state.filter = event.target.value;
        render();
      });

      refresh();
      setInterval(refresh, 30000);

      // ── Opening search ─────────────────────────────────────────────────────

      const KNOWN_OPENINGS = ["Alekhine's Defense","Benoni Defense","Bird's Opening","Budapest Gambit","Caro-Kann Defense","Catalan Opening","Dutch Defense","English Opening","Four Knights Game","French Defense","Gr\\u00fcnfeld Defense","Italian Game","King's Gambit","King's Indian Defense","London System","Nimzo-Indian Defense","Petrov's Defense","Pirc Defense","Queen's Gambit","Queen's Indian Defense","R\\u00e9ti Opening","Ruy Lopez","Scandinavian Defense","Scotch Game","Semi-Slav Defense","Sicilian Defense","Sicilian Dragon","Sicilian Najdorf","Sicilian Scheveningen","Slav Defense","Vienna Game"];

      const openingInputEl = document.getElementById('opening-input');
      const searchBtnEl = document.getElementById('search-btn');
      const searchStatusEl = document.getElementById('search-status');
      const searchResultsEl = document.getElementById('search-results');

      const searchState = { results: [], sort: 'rating', refreshTimer: null };

      const datalist = document.getElementById('opening-suggestions');
      for (const name of KNOWN_OPENINGS.sort()) {
        const opt = document.createElement('option');
        opt.value = name;
        datalist.appendChild(opt);
      }

      async function searchOpenings() {
        const query = openingInputEl.value.trim();
        if (!query) return;

        searchBtnEl.disabled = true;
        searchStatusEl.className = 'search-status';
        searchStatusEl.textContent = `Searching for "${query}"…`;
        searchResultsEl.innerHTML = '';

        try {
          const res = await fetch(`/api/search?opening=${encodeURIComponent(query)}`);
          if (!res.ok) {
            const text = await res.text();
            throw new Error(text || `Search API error (${res.status})`);
          }
          const games = await res.json();

          if (!Array.isArray(games) || !games.length) {
            searchStatusEl.textContent = `No recent games found for "${query}" this month.`;
            searchResultsEl.innerHTML = '';
            return;
          }

          searchState.results = games;
          renderSearchResults();

          const liveCount = games.filter(g => g.isLive).length;
          if (liveCount > 0) {
            searchStatusEl.textContent =
              `${liveCount} live game${liveCount !== 1 ? 's' : ''} · ${games.length} total recent · auto-refreshes every 30 s`;
          } else {
            searchStatusEl.textContent =
              `No live games currently — showing ${games.length} most recent · auto-refreshes every 30 s`;
          }

          if (searchState.refreshTimer) clearInterval(searchState.refreshTimer);
          searchState.refreshTimer = setInterval(searchOpenings, 30000);
        } catch (err) {
          searchStatusEl.textContent = `Error: ${err.message}`;
          searchStatusEl.className = 'search-status error';
        } finally {
          searchBtnEl.disabled = false;
        }
      }

      function renderSearchResults() {
        if (!searchState.results.length) {
          searchResultsEl.innerHTML = '<p class="muted">No games found.</p>';
          return;
        }

        const sorted = [...searchState.results].sort((a, b) => {
          if (searchState.sort === 'rating') {
            if (a.isLive !== b.isLive) return a.isLive ? -1 : 1;
            return b.avgRating - a.avgRating;
          }
          return b.createdAt - a.createdAt;
        });

        searchResultsEl.innerHTML = sorted.map(game => {
          const statusBadge = game.isLive
            ? '<span class="live-badge">&#9679; LIVE</span>'
            : '<span class="recent-badge">Recent</span>';
          const openingLabel = game.eco
            ? `${htmlEscape(game.eco)} ${htmlEscape(game.opening)}`
            : htmlEscape(game.opening);
          const players =
            `${htmlEscape(game.white)} (${game.whiteRating}) vs ${htmlEscape(game.black)} (${game.blackRating})`;
          return `
            <div class="game-card">
              <div class="game-card-left">
                <div class="game-players">
                  <a href="${htmlEscape(game.url)}" target="_blank" rel="noopener noreferrer">${players}</a>
                </div>
                <div class="opening-label">${openingLabel}</div>
              </div>
              <div class="game-card-right">
                <span class="rating-badge">&#11088; ${game.avgRating}</span>
                ${statusBadge}
              </div>
            </div>
          `;
        }).join('');
      }

      document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          searchState.sort = btn.dataset.sort;
          renderSearchResults();
        });
      });

      function triggerSearch() {
        if (searchState.refreshTimer) {
          clearInterval(searchState.refreshTimer);
          searchState.refreshTimer = null;
        }
        searchOpenings();
      }

      searchBtnEl.addEventListener('click', triggerSearch);
      openingInputEl.addEventListener('keydown', e => { if (e.key === 'Enter') triggerSearch(); });
    </script>
  </body>
</html>
"""


def render_stats_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Opening Stats · Chess Openings Live</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f4f6fb;
        --card: #ffffff;
        --text: #1b1f2a;
        --muted: #5f6b85;
        --accent: #3558d6;
        --border: #e3e8f4;
        --shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
      }
      * { box-sizing: border-box; }
      body { font-family: "Inter", "Segoe UI", sans-serif; margin: 0; background: var(--bg); color: var(--text); }
      .page { max-width: 960px; margin: 0 auto; padding: 32px 24px 56px; }
      header { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; margin-bottom: 24px; }
      h1 { margin: 0; font-size: 1.8rem; }
      a { color: var(--accent); text-decoration: none; font-weight: 600; }
      a:hover { text-decoration: underline; }
      .card { background: var(--card); border-radius: 14px; padding: 16px; box-shadow: var(--shadow); border: 1px solid var(--border); }
      canvas { width: 100%; height: 420px; }
      .meta { color: var(--muted); margin-top: 8px; }
    </style>
  </head>
  <body>
    <div class="page">
      <header>
        <h1>Opening stats</h1>
        <a href="/">Back to live openings</a>
      </header>
      <div class="card">
        <canvas id="chart"></canvas>
        <div id="updated" class="meta"></div>
      </div>
    </div>
    <script>
      const canvas = document.getElementById('chart');
      const ctx = canvas.getContext('2d');
      const updatedEl = document.getElementById('updated');
      let latestRows = [];

      function resizeCanvas() {
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * window.devicePixelRatio;
        canvas.height = rect.height * window.devicePixelRatio;
        ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
      }

      function drawChart(rows) {
        resizeCanvas();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!rows.length) {
          ctx.fillStyle = '#5f6b85';
          ctx.font = '16px sans-serif';
          ctx.fillText('No stats yet. Refresh live openings to collect data.', 16, 32);
          return;
        }
        const padding = 24;
        const barGap = 8;
        const barHeight = 22;
        const maxBars = Math.min(rows.length, 15);
        const visible = rows.slice(0, maxBars);
        const maxValue = Math.max(...visible.map(row => row.count), 1);
        const chartWidth = canvas.getBoundingClientRect().width - padding * 2 - 140;
        visible.forEach((row, index) => {
          const y = padding + index * (barHeight + barGap);
          const barWidth = Math.round((row.count / maxValue) * chartWidth);
          ctx.fillStyle = '#eef2ff';
          ctx.fillRect(padding + 140, y, chartWidth, barHeight);
          ctx.fillStyle = '#3558d6';
          ctx.fillRect(padding + 140, y, barWidth, barHeight);
          ctx.fillStyle = '#1b1f2a';
          ctx.font = '14px sans-serif';
          ctx.fillText(row.opening, padding, y + 16);
          ctx.fillStyle = '#5f6b85';
          ctx.fillText(row.count.toString(), padding + 140 + chartWidth + 8, y + 16);
        });
      }

      async function loadStats() {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        const rows = Object.entries(stats.openings || {})
          .map(([opening, count]) => ({ opening, count }))
          .sort((a, b) => b.count - a.count);
        updatedEl.textContent = stats.updated_at ? `Last updated ${stats.updated_at}` : '';
        latestRows = rows;
        drawChart(rows);
      }

      window.addEventListener('resize', () => drawChart(latestRows));
      loadStats();
    </script>
  </body>
</html>
"""


def serve_openings(
    client: LichessClient,
    port: int,
    limit: int | None,
    source: str,
    stats_path: Path,
) -> int:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            allowed = {"/", "/api/openings", "/stats", "/api/stats", "/api/search"}
            if path not in allowed:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            stats = load_stats(stats_path)
            games: list[LiveGame] = []
            if path in ("/", "/api/openings"):
                try:
                    games = fetch_openings(client, limit, source)
                    stats = update_stats(stats, games)
                    save_stats(stats_path, stats)
                except RuntimeError as error:
                    message = (
                        "Unable to reach the Lichess API. "
                        "Check your internet connection or firewall settings."
                    )
                    body = f"{message}\n\nDetails: {error}\n"
                    response = body.encode("utf-8")
                    self.send_response(HTTPStatus.BAD_GATEWAY)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    try:
                        self.wfile.write(response)
                    except BrokenPipeError:
                        return
                    return
            if path == "/api/search":
                params = parse_qs(parsed.query)
                opening_name = params.get("opening", [""])[0].strip()
                if not opening_name:
                    err = b'{"error": "Missing opening query parameter"}'
                    self.send_response(HTTPStatus.BAD_REQUEST)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err)))
                    self.end_headers()
                    try:
                        self.wfile.write(err)
                    except BrokenPipeError:
                        return
                    return
                try:
                    results = search_live_games_by_opening(client, opening_name)
                except RuntimeError as error:
                    message = (
                        "Unable to reach the Lichess API. "
                        "Check your internet connection or firewall settings."
                    )
                    body = f"{message}\n\nDetails: {error}\n"
                    response = body.encode("utf-8")
                    self.send_response(HTTPStatus.BAD_GATEWAY)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    try:
                        self.wfile.write(response)
                    except BrokenPipeError:
                        return
                    return
                response = json.dumps(results, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                try:
                    self.wfile.write(response)
                except BrokenPipeError:
                    return
                return
            if path == "/stats":
                html = render_stats_html().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                try:
                    self.wfile.write(html)
                except BrokenPipeError:
                    return
                return
            if path == "/api/stats":
                response = json.dumps(stats, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                try:
                    self.wfile.write(response)
                except BrokenPipeError:
                    return
                return
            payload = build_openings_payload(games)
            if path == "/api/openings":
                response = json.dumps(payload, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                try:
                    self.wfile.write(response)
                except BrokenPipeError:
                    return
                return
            html = render_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            try:
                self.wfile.write(html)
            except BrokenPipeError:
                return

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Serving on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


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
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run a local web server to browse openings",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port for --serve (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--source",
        choices=("tv", "broadcast", "auto"),
        default="auto",
        help="Data source for live games (default: auto)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw Lichess API payloads for debugging",
    )
    parser.add_argument(
        "--stats-file",
        type=Path,
        default=Path(DEFAULT_STATS_FILE),
        help=f"Path to stats JSON file (default: {DEFAULT_STATS_FILE})",
    )
    parser.add_argument(
        "--search-opening",
        metavar="NAME",
        default=None,
        help=(
            "Search for live/recent Lichess games by opening name "
            "(e.g. \"King's Gambit\"). Results are sorted by average player rating."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    client = LichessClient(debug=args.debug)

    if args.serve:
        return serve_openings(
            client, args.port, args.limit, args.source, args.stats_file
        )

    if args.search_opening:
        resolved = resolve_opening_moves(args.search_opening)
        if resolved is None:
            known = ", ".join(sorted(OPENING_MOVES))
            print(
                f"Unknown opening: {args.search_opening!r}\n"
                f"Known openings: {known}",
                file=sys.stderr,
            )
            return 1
        canonical_name, _ = resolved
        try:
            results = search_live_games_by_opening(client, args.search_opening)
        except RuntimeError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            live = [g for g in results if g["isLive"]]
            recent = [g for g in results if not g["isLive"]]
            print(f"\n{canonical_name}")
            if live:
                print(f"\n  Live games ({len(live)}):")
                for g in live:
                    print(
                        f"    {g['white']} ({g['whiteRating']}) vs "
                        f"{g['black']} ({g['blackRating']})  "
                        f"avg {g['avgRating']}  {g['url']}"
                    )
            else:
                print("\n  No live games currently.")
            if recent:
                print(f"\n  Recent games ({len(recent)}):")
                for g in recent:
                    print(
                        f"    {g['white']} ({g['whiteRating']}) vs "
                        f"{g['black']} ({g['blackRating']})  "
                        f"avg {g['avgRating']}  {g['url']}"
                    )
        return 0

    while True:
        try:
            games = fetch_openings(client, args.limit, args.source)
            stats = load_stats(args.stats_file)
            stats = update_stats(stats, games)
            save_stats(args.stats_file, stats)
        except RuntimeError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
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
