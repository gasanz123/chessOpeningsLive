# Chess Openings Live

Chess Openings Live is a concept for a website that organizes **live chess games** by the **opening** currently being played, so observers can browse openings and jump directly to active games.

## Core Idea
- Ingest live games from providers (e.g., Lichess, Chess.com, FIDE, or tournament PGN feeds).
- Parse each live game in real time and classify the opening (ECO + name) from the current move sequence.
- Present an opening-centric navigation UI that shows which openings are being played **right now**, with quick links to the relevant live boards.

## Lichess Ingestion (Prototype)
This repo includes a small script that pulls the current Lichess TV games and groups them by opening.

### Run
```bash
python scripts/lichess_openings.py
```

Optional flags:
- `--poll-interval 30` to refresh every 30 seconds.
- `--limit 5` to limit the number of TV channels queried.
- `--json` to emit raw JSON for downstream processing.
- `--serve` to run a local web server for browsing openings.
- `--port 8000` to change the server port.
- `--source auto|tv|broadcast` to select the Lichess data source (default: `auto`).
- `--debug` to print raw Lichess API payloads for troubleshooting.

### Open in the Browser
```bash
python scripts/lichess_openings.py --serve
```

Then open http://localhost:8000 to browse openings with active games.
If the page shows a gateway error, it usually means the Lichess API could not be reached
(for example, due to firewalls, proxies, or missing internet access).

The browser view refreshes every 30 seconds and includes a filter box so you can quickly
search openings or player names.

The server also stores cumulative opening counts in a local JSON file and exposes a stats
page at http://localhost:8000/stats.

If Lichess TV is empty in your region, try the broadcast feed:
```bash
python scripts/lichess_openings.py --serve --source broadcast
```

To capture the raw Lichess TV payload for debugging:
```bash
python scripts/lichess_openings.py --debug --limit 1
```

## High-Level Workflow
1. **Live game ingestion**
   - Subscribe to provider APIs or PGN streams.
   - Normalize incoming game metadata (players, time control, event, rating, etc.).
2. **Opening classification**
   - Maintain a local ECO/opening database (PGN move trees + names).
   - Match the current move list to the deepest known opening variation.
   - Update classification as new moves arrive.
3. **Aggregation + indexing**
   - Group active games by opening name/ECO code.
   - Track counts and expose a fast search index.
4. **Observer UI**
   - Opening list with counts and quick filters (ECO, name, popularity, rating, time control).
   - A live games grid/board view for a selected opening.

## Data Model (Draft)
- **Game**
  - `id`, `source`, `players`, `ratings`, `time_control`, `moves`, `status`, `last_update`
- **Opening**
  - `eco_code`, `name`, `aliases`, `pgn_sequence`
- **GameOpeningIndex**
  - `game_id`, `eco_code`, `opening_name`, `matched_ply`

## MVP Feature Set
- Live ingestion from a single source.
- Opening classification with ECO + human-readable name.
- UI that lists openings with active games and lets the observer click into a live board.

## Possible Tech Stack
- **Backend**: Node.js + WebSocket ingest + Redis for live state
- **Opening classifier**: ECO PGN database + trie matcher
- **Frontend**: React + real-time updates (WebSocket/SSE)

## Next Steps
- Choose initial live data source.
- Implement the opening matcher and ECO database loader.
- Build the first UI with opening list + live game viewer.
