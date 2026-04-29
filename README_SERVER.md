# Chess Openings Live - Web Server Setup

This project now includes API key integration and a Python web server backend.

## Quick Start

1. **Start the Python web server:**
   ```bash
   python start_server.py
   ```
   This will start the server on `http://localhost:8000`

2. **Open the web interface:**
   Navigate to `http://localhost:8000` in your browser

3. **Optional: Add your Lichess API key:**
   - Enter your API key in the "Lichess API key (optional)" field
   - The API key allows higher rate limits and access to more features
   - Get your API key from: https://lichess.org/account/oauth/token

## Features

- **Live TV games**: Shows current Lichess TV games grouped by opening
- **Opening search**: Search for live/recent games by opening name
- **API key support**: Optional authentication for better rate limits
- **Auto-refresh**: Data updates every 30 seconds
- **Opening stats**: View statistics at `/stats`

## API Endpoints

- `GET /` - Main HTML interface
- `GET /api/openings` - JSON of current live games
- `GET /api/search?opening=<name>` - Search games by opening
- `GET /api/stats` - Opening statistics
- `GET /stats` - Statistics HTML page

## API Key Usage

The API key is optional but recommended:
- Without API key: Limited to public Lichess API rates
- With API key: Higher rate limits, access to more features
- The key is stored locally in your browser only

## Development

To run with custom options:
```bash
python scripts/lichess_openings.py --serve --port 8080 --debug
```

Available options:
- `--port <number>`: Custom port (default: 8000)
- `--debug`: Enable debug output
- `--source tv|broadcast|auto`: Data source selection
- `--limit <number>`: Limit number of channels to check
