#!/usr/bin/env python3
"""Poll Lichess TV channels and group live games by opening."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LICHESS_TV_URL = "https://lichess.org/api/tv/channels"
LICHESS_GAME_EXPORT = "https://lichess.org/game/export/{game_id}"
DEFAULT_PORT = 8000


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
    def __init__(self) -> None:
        self.user_agent = "ChessOpeningsLive/0.1"

    def _fetch_json(self, url: str, params: dict[str, str] | None = None) -> dict:
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
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"Failed to fetch {url}: {error}") from error

    def fetch_tv_channels(self) -> list[dict]:
        data = self._fetch_json(LICHESS_TV_URL)
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


def fetch_openings(client: LichessClient, limit: int | None) -> Iterable[LiveGame]:
    channels = client.fetch_tv_channels()
    if limit is not None:
        channels = channels[:limit]
    for channel in channels:
        game_id = extract_game_id(channel)
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


def build_openings_payload(games: Iterable[LiveGame]) -> list[dict]:
    grouped: dict[str, list[LiveGame]] = {}
    for game in games:
        grouped.setdefault(format_opening_key(game), []).append(game)

    payload = []
    for opening, opening_games in sorted(
        grouped.items(), key=lambda item: len(item[1]), reverse=True
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


def render_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Chess Openings Live</title>
    <style>
      body { font-family: sans-serif; margin: 32px; background: #f7f7f9; }
      h1 { margin-bottom: 8px; }
      .meta { color: #555; margin-bottom: 24px; }
      .controls { margin-bottom: 16px; display: flex; gap: 12px; align-items: center; }
      .controls input { padding: 8px 10px; border-radius: 6px; border: 1px solid #ccc; width: 280px; }
      .opening { background: white; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
      .opening h2 { margin: 0 0 8px 0; font-size: 1.1rem; }
      .count { color: #666; font-weight: normal; }
      ul { margin: 0; padding-left: 18px; }
      li { margin-bottom: 6px; }
      a { color: #1a4ae0; text-decoration: none; }
      a:hover { text-decoration: underline; }
      .channel { color: #666; }
      .muted { color: #777; }
      .error { background: #fff2f2; border: 1px solid #f2c0c0; padding: 12px; border-radius: 8px; }
    </style>
  </head>
  <body>
    <h1>Chess Openings Live</h1>
    <p class="meta">Live games grouped by opening (Lichess TV).</p>
    <div class="controls">
      <input id="filter" type="text" placeholder="Filter openings or players" />
      <span id="summary" class="muted"></span>
    </div>
    <div id="status" class="muted">Loading live games…</div>
    <div id="openings"></div>
    <script>
      const state = { openings: [], filter: '' };
      const openingsEl = document.getElementById('openings');
      const statusEl = document.getElementById('status');
      const summaryEl = document.getElementById('summary');
      const filterEl = document.getElementById('filter');

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
              `<li><a href="${game.url}" target="_blank">${game.players}</a> <span class="channel">[${game.channel}]</span></li>`
            )).join('');
            return `
              <section class="opening">
                <h2>${opening.opening} <span class="count">(${opening.count})</span></h2>
                <ul>${gamesHtml}</ul>
              </section>
            `;
          }).join('');
        }
        const totalGames = filtered.reduce((sum, opening) => sum + opening.count, 0);
        summaryEl.textContent = `${filtered.length} openings · ${totalGames} games`;
      }

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
    </script>
  </body>
</html>
"""


def serve_openings(client: LichessClient, port: int, limit: int | None) -> int:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in ("/", "/api/openings"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                games = list(fetch_openings(client, limit))
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
                self.wfile.write(response)
                return
            payload = build_openings_payload(games)
            if self.path == "/api/openings":
                response = json.dumps(payload, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            html = render_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

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
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    client = LichessClient()

    if args.serve:
        return serve_openings(client, args.port, args.limit)

    while True:
        try:
            games = list(fetch_openings(client, args.limit))
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
