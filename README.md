# Owen Dashboard

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![No Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)

Unified visibility dashboard for Owen's tasks, heartbeat logs, and activity.

## Features

- **📊 Overview** - Stats, throughput charts, action breakdown
- **📋 Tasks** - Full kanban board (7 states)
- **📜 Logs** - Recent heartbeat cycle history
- **⏱️ Timeline** - Combined activity feed

## Quick Start

```bash
python3 server.py
# Open http://localhost:8766
```

## Options

```bash
python3 server.py --port 8080 --workspace /path/to/workspace
```

## Environment

- `WORKSPACE` - Path to Owen workspace (default: `/Users/Shared/owen/workspace`)

## Deployment

### Local (launchd)

```bash
# Install as system service
sudo ./install-service.sh
```

### Docker

```bash
docker build -t owen-dashboard .
docker run -p 8766:8766 -v /path/to/workspace:/workspace owen-dashboard
```

### Fly.io / Railway / etc.

The server is stateless and reads from the workspace directory. Mount or sync the workspace for live data.

## Views

| View | URL | Description |
|------|-----|-------------|
| Overview | `/?view=overview` | Stats, charts, in-progress tasks |
| Tasks | `/?view=tasks` | Full kanban board |
| Logs | `/?view=logs` | Heartbeat cycle history |
| Timeline | `/?view=timeline` | Combined activity feed |

## Data Sources

- `tasks/{open,doing,review,done,blocked-*}/` - Task markdown files
- `memory/heartbeat-logs/heartbeat-YYYY-MM-DD.jsonl` - Heartbeat logs

## Tech

- Python 3.10+ (stdlib only, no dependencies)
- Auto-refresh every 30 seconds
- Dark theme
- Responsive grid layout
