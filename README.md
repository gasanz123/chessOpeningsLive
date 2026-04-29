# Chess Openings Live

Chess Openings Live organizes **live chess games** by the **opening** currently being played, so observers can browse openings and jump directly to active games.

## 🚀 Quick Start

### GitHub Pages (Recommended)
The easiest way to use this project is via GitHub Pages:
1. Open `https://[your-username].github.io/chessOpeningsLive/`
2. Optionally add your Lichess API key for better rate limits
3. Browse live games grouped by opening

### Local Development
```bash
python scripts/lichess_openings.py --serve
```
Then open http://localhost:8000

## 🎯 Features

- **Live TV games**: Shows current Lichess TV games grouped by opening
- **Opening search**: Search for live/recent games by opening name  
- **API key support**: Optional authentication for better rate limits
- **Auto-refresh**: Data updates every 30 seconds
- **GitHub Pages ready**: Works as a static site for easy deployment

## 🔑 API Key Usage

The API key is optional but recommended:
- **Without API key**: Limited to public Lichess API rates
- **With API key**: Higher rate limits, access to more features
- **Get your key**: https://lichess.org/account/oauth/token
- **Security**: Key is stored locally in your browser only

## 📁 Deployment Options

### GitHub Pages (Static Site)
- ✅ No server required
- ✅ Free hosting
- ✅ Direct Lichess API calls from browser
- ✅ API key authentication supported
- ❌ No server-side features (stats page, etc.)

### Local Server (Full Features)
- ✅ All GitHub Pages features
- ✅ Opening statistics page
- ✅ Better error handling
- ✅ Debug capabilities
- ❌ Requires Python server

## 🛠️ Local Development Commands

```bash
# Start local server with all features
python scripts/lichess_openings.py --serve

# Custom port
python scripts/lichess_openings.py --serve --port 8080

# Debug mode
python scripts/lichess_openings.py --serve --debug

# Use broadcast source instead of TV
python scripts/lichess_openings.py --serve --source broadcast

# Quick start script
python start_server.py
```

## 🌐 API Endpoints (Local Server Only)

- `GET /` - Main HTML interface
- `GET /api/openings` - JSON of current live games
- `GET /api/search?opening=<name>` - Search games by opening
- `GET /api/stats` - Opening statistics
- `GET /stats` - Statistics HTML page

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
