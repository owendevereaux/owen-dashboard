#!/usr/bin/env python3
"""
Owen Dashboard - Unified visibility into tasks, logs, and agent activity.

Run: python server.py [--port PORT] [--workspace PATH]

Provides:
- Task board (all 7 states)
- Heartbeat cycle logs
- Activity timeline
- Stats and throughput
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_WORKSPACE = Path(os.environ.get("WORKSPACE", "/Users/Shared/owen/workspace"))
DEFAULT_PORT = 8766

TASK_STATES = ['doing', 'open', 'review', 'blocked-joe', 'blocked-owen', 'wont-do', 'done']

# ─────────────────────────────────────────────────────────────────────────────
# Task Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_task(filepath: Path) -> dict:
    """Parse a task markdown file."""
    content = filepath.read_text()
    lines = content.split('\n')
    
    title = filepath.stem
    for line in lines:
        if line.startswith('# '):
            title = line[2:].strip()
            break
    
    priority = 'P3'
    if match := re.search(r'\(P(\d)\)', title):
        priority = f'P{match.group(1)}'
    elif filepath.stem.startswith('p'):
        priority = filepath.stem[:2].upper()
    
    summary = ''
    in_summary = False
    for line in lines:
        if line.startswith('## Summary'):
            in_summary = True
            continue
        if in_summary:
            if line.startswith('## ') or line.startswith('# '):
                break
            summary += line + '\n'
    
    blocked_info = ''
    in_blocked = False
    for line in lines:
        if line.startswith('## Blocked'):
            in_blocked = True
            continue
        if in_blocked:
            if line.startswith('## ') or line.startswith('# ') or line.startswith('---'):
                break
            blocked_info += line + '\n'
    
    completed = None
    if 'done' in str(filepath):
        if match := re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}-\d{2})', filepath.stem):
            completed = match.group(1).replace('T', ' ').replace('-', ':', 2)
    
    mtime = filepath.stat().st_mtime
    age_seconds = datetime.now().timestamp() - mtime
    
    return {
        'file': filepath.name,
        'title': title,
        'priority': priority,
        'summary': summary.strip(),
        'blocked_info': blocked_info.strip(),
        'completed': completed,
        'mtime': datetime.fromtimestamp(mtime).isoformat(),
        'age_seconds': age_seconds
    }

def get_tasks(workspace: Path) -> dict:
    """Get all tasks organized by status."""
    tasks_dir = workspace / "tasks"
    tasks = {state: [] for state in TASK_STATES}
    
    for status in TASK_STATES:
        status_dir = tasks_dir / status
        if status_dir.exists():
            for f in sorted(status_dir.glob('*.md'), reverse=(status == 'done')):
                if f.name != 'TEMPLATE.md':
                    tasks[status].append(parse_task(f))
    
    return tasks

# ─────────────────────────────────────────────────────────────────────────────
# Log Parsing
# ─────────────────────────────────────────────────────────────────────────────

def get_heartbeat_logs(workspace: Path, days: int = 7) -> list:
    """Get heartbeat logs for the last N days."""
    logs_dir = workspace / "memory" / "heartbeat-logs"
    if not logs_dir.exists():
        return []
    
    all_entries = []
    
    for i in range(days):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        log_file = logs_dir / f"heartbeat-{day}.jsonl"
        
        if log_file.exists():
            with open(log_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            entry['_day'] = day
                            all_entries.append(entry)
                        except json.JSONDecodeError:
                            continue
    
    # Sort by timestamp descending
    all_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return all_entries

def get_log_stats(logs: list) -> dict:
    """Compute statistics from logs."""
    if not logs:
        return {'total_cycles': 0}
    
    action_counts = {}
    category_counts = {}
    hourly_counts = {}
    daily_counts = {}
    
    for entry in logs:
        # Count actions
        action_id = entry.get('action_id', 'unknown')
        action_counts[action_id] = action_counts.get(action_id, 0) + 1
        
        # Count categories
        category = entry.get('category', 'unknown')
        category_counts[category] = category_counts.get(category, 0) + 1
        
        # Count by hour
        ts = entry.get('timestamp', '')
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                hour = dt.strftime('%Y-%m-%d %H:00')
                hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
                day = dt.strftime('%Y-%m-%d')
                daily_counts[day] = daily_counts.get(day, 0) + 1
            except:
                pass
    
    return {
        'total_cycles': len(logs),
        'action_counts': dict(sorted(action_counts.items(), key=lambda x: -x[1])),
        'category_counts': dict(sorted(category_counts.items(), key=lambda x: -x[1])),
        'hourly_counts': hourly_counts,
        'daily_counts': daily_counts,
    }

def get_throughput_data(workspace: Path, days: int = 7) -> list:
    """Get task completion counts for the last N days."""
    done_dir = workspace / "tasks" / "done"
    if not done_dir.exists():
        return []
    
    counts = {}
    for i in range(days):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        counts[day] = 0
    
    for f in done_dir.glob('*.md'):
        if match := re.match(r'(\d{4}-\d{2}-\d{2})', f.stem):
            day = match.group(1)
            if day in counts:
                counts[day] += 1
    
    return [(day, counts[day]) for day in sorted(counts.keys())]

# ─────────────────────────────────────────────────────────────────────────────
# HTML Rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_dashboard(workspace: Path, view: str = 'overview') -> str:
    """Render the main dashboard HTML."""
    tasks = get_tasks(workspace)
    logs = get_heartbeat_logs(workspace, days=7)
    stats = get_log_stats(logs)
    throughput = get_throughput_data(workspace, 7)
    
    # Task counts
    task_counts = {state: len(tasks[state]) for state in TASK_STATES}
    today = datetime.now().strftime('%Y-%m-%d')
    done_today = sum(1 for t in tasks['done'] if t['completed'] and today in t['completed'])
    
    # Navigation
    nav_items = [
        ('overview', '📊 Overview'),
        ('tasks', '📋 Tasks'),
        ('logs', '📜 Logs'),
        ('timeline', '⏱️ Timeline'),
    ]
    nav_html = ''.join(
        f'<a href="?view={v}" class="nav-item {"active" if view == v else ""}">{label}</a>'
        for v, label in nav_items
    )
    
    # Build content based on view
    if view == 'tasks':
        content = render_tasks_view(tasks)
    elif view == 'logs':
        content = render_logs_view(logs[:100])  # Last 100 entries
    elif view == 'timeline':
        content = render_timeline_view(logs[:50], tasks)
    else:
        content = render_overview(tasks, stats, throughput, done_today)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Owen Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; 
            color: #e2e8f0;
            min-height: 100vh;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; padding: 1rem; }}
        
        /* Header */
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 0;
            border-bottom: 1px solid #334155;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }}
        h1 {{ font-size: 1.5rem; font-weight: 600; }}
        .nav {{ display: flex; gap: 0.5rem; }}
        .nav-item {{
            padding: 0.5rem 1rem;
            background: #1e293b;
            border-radius: 0.5rem;
            color: #94a3b8;
            text-decoration: none;
            font-size: 0.875rem;
            transition: all 0.2s;
        }}
        .nav-item:hover {{ background: #334155; color: #e2e8f0; }}
        .nav-item.active {{ background: #3b82f6; color: white; }}
        .updated {{ font-size: 0.75rem; color: #64748b; }}
        
        /* Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .stat-card {{
            background: #1e293b;
            border-radius: 0.5rem;
            padding: 1rem;
            text-align: center;
        }}
        .stat-value {{ font-size: 2rem; font-weight: 700; }}
        .stat-label {{ font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem; }}
        
        /* Charts */
        .chart-container {{
            background: #1e293b;
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1.5rem;
        }}
        .chart-title {{ font-size: 0.875rem; font-weight: 600; margin-bottom: 1rem; }}
        .bar-chart {{
            display: flex;
            align-items: flex-end;
            gap: 0.5rem;
            height: 100px;
        }}
        .bar-item {{
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .bar {{
            width: 100%;
            background: #3b82f6;
            border-radius: 4px 4px 0 0;
            min-height: 4px;
            transition: height 0.3s;
        }}
        .bar-value {{ font-size: 0.7rem; margin-top: 0.25rem; }}
        .bar-label {{ font-size: 0.6rem; color: #64748b; }}
        
        /* Columns (Tasks) */
        .columns {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            align-items: start;
        }}
        .column {{
            background: #1e293b;
            border-radius: 0.5rem;
            padding: 0.75rem;
            min-height: 200px;
        }}
        .column-header {{
            font-weight: 600;
            font-size: 0.85rem;
            margin-bottom: 0.75rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #334155;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .count {{ 
            background: #334155;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            font-size: 0.7rem;
        }}
        
        /* Task Cards */
        .task-card {{
            background: #0f172a;
            border-radius: 0.375rem;
            padding: 0.6rem;
            margin-bottom: 0.5rem;
            border: 1px solid #334155;
            font-size: 0.8rem;
        }}
        .task-card:hover {{ border-color: #475569; }}
        .task-header {{
            display: flex;
            align-items: center;
            gap: 0.4rem;
            flex-wrap: wrap;
        }}
        .priority {{
            font-size: 0.6rem;
            font-weight: 700;
            padding: 0.1rem 0.3rem;
            border-radius: 0.25rem;
            color: white;
        }}
        .title {{ font-weight: 500; flex: 1; font-size: 0.8rem; }}
        .completed {{ font-size: 0.65rem; color: #22c55e; }}
        .summary {{ font-size: 0.7rem; color: #94a3b8; margin-top: 0.4rem; line-height: 1.3; }}
        .blocked-info {{ font-size: 0.7rem; color: #f97316; margin-top: 0.4rem; }}
        .empty {{ color: #64748b; font-style: italic; padding: 1rem; text-align: center; }}
        
        /* Log Entries */
        .log-list {{ display: flex; flex-direction: column; gap: 0.5rem; }}
        .log-entry {{
            background: #1e293b;
            border-radius: 0.5rem;
            padding: 0.75rem 1rem;
            display: grid;
            grid-template-columns: auto 1fr auto;
            gap: 1rem;
            align-items: center;
            font-size: 0.85rem;
        }}
        .log-time {{ color: #64748b; font-size: 0.75rem; white-space: nowrap; }}
        .log-action {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .log-action-id {{
            background: #334155;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-family: monospace;
            font-size: 0.75rem;
        }}
        .log-reason {{ color: #94a3b8; font-size: 0.75rem; }}
        .log-category {{
            font-size: 0.7rem;
            padding: 0.2rem 0.5rem;
            border-radius: 0.25rem;
            background: #1e293b;
            border: 1px solid #334155;
        }}
        
        /* Timeline */
        .timeline {{
            position: relative;
            padding-left: 2rem;
        }}
        .timeline::before {{
            content: '';
            position: absolute;
            left: 0.5rem;
            top: 0;
            bottom: 0;
            width: 2px;
            background: #334155;
        }}
        .timeline-item {{
            position: relative;
            padding: 0.75rem 0;
            padding-left: 1rem;
        }}
        .timeline-item::before {{
            content: '';
            position: absolute;
            left: -1.5rem;
            top: 1rem;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #3b82f6;
        }}
        .timeline-item.task::before {{ background: #22c55e; }}
        .timeline-item.heartbeat::before {{ background: #6366f1; }}
        .timeline-time {{ font-size: 0.7rem; color: #64748b; }}
        .timeline-content {{ margin-top: 0.25rem; }}
        
        /* Action breakdown */
        .action-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 0.5rem;
            margin-top: 1rem;
        }}
        .action-item {{
            display: flex;
            justify-content: space-between;
            padding: 0.5rem;
            background: #0f172a;
            border-radius: 0.25rem;
            font-size: 0.8rem;
        }}
        .action-name {{ font-family: monospace; }}
        .action-count {{ color: #3b82f6; font-weight: 600; }}
        
        /* Section headers */
        .section {{ margin-bottom: 1.5rem; }}
        .section-title {{
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        /* Two column layout */
        .two-col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }}
        @media (max-width: 900px) {{
            .two-col {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🦉 Owen Dashboard</h1>
            <nav class="nav">{nav_html}</nav>
            <span class="updated">Updated: {datetime.now().strftime('%H:%M:%S')}</span>
        </header>
        
        {content}
    </div>
</body>
</html>'''

def render_overview(tasks: dict, stats: dict, throughput: list, done_today: int) -> str:
    """Render the overview page."""
    task_counts = {state: len(tasks[state]) for state in TASK_STATES}
    
    # Throughput chart
    max_count = max((c for _, c in throughput), default=1) or 1
    bars_html = ''
    for day, count in throughput:
        height = (count / max_count) * 100
        day_short = day[5:]  # MM-DD
        bars_html += f'''
        <div class="bar-item">
            <div class="bar" style="height: {height}%"></div>
            <span class="bar-value">{count}</span>
            <span class="bar-label">{day_short}</span>
        </div>'''
    
    # Action breakdown
    action_html = ''
    for action, count in list(stats.get('action_counts', {}).items())[:10]:
        action_html += f'<div class="action-item"><span class="action-name">{action}</span><span class="action-count">{count}</span></div>'
    
    return f'''
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value" style="color: #ef4444">{task_counts['doing']}</div>
            <div class="stat-label">In Progress</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #22c55e">{task_counts['open']}</div>
            <div class="stat-label">Open</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #eab308">{task_counts['review']}</div>
            <div class="stat-label">Review</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #f97316">{task_counts['blocked-joe']}</div>
            <div class="stat-label">Blocked (Joe)</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{done_today}</div>
            <div class="stat-label">Done Today</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #6366f1">{stats.get('total_cycles', 0)}</div>
            <div class="stat-label">Heartbeats (7d)</div>
        </div>
    </div>
    
    <div class="two-col">
        <div class="chart-container">
            <div class="chart-title">📈 Task Throughput (7 days)</div>
            <div class="bar-chart">{bars_html}</div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">🎯 Top Actions (7 days)</div>
            <div class="action-grid">{action_html}</div>
        </div>
    </div>
    
    <div class="section">
        <div class="section-title">🔨 Currently In Progress</div>
        <div class="columns" style="grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));">
            {render_task_cards(tasks['doing'], 'doing')}
        </div>
    </div>
    '''

def render_task_cards(task_list: list, status: str) -> str:
    """Render task cards."""
    if not task_list:
        return '<div class="empty">No tasks</div>'
    
    priority_colors = {'P1': '#ef4444', 'P2': '#f59e0b', 'P3': '#3b82f6', 'P4': '#6b7280'}
    cards = ''
    
    for task in task_list[:20]:  # Limit to 20
        color = priority_colors.get(task['priority'], '#6b7280')
        
        info_html = ''
        if task.get('blocked_info'):
            info_html = f'<div class="blocked-info">{task["blocked_info"][:100]}...</div>'
        elif task.get('summary'):
            info_html = f'<div class="summary">{task["summary"][:100]}...</div>'
        
        completed_html = ''
        if task.get('completed'):
            completed_html = f'<span class="completed">✓ {task["completed"]}</span>'
        
        cards += f'''
        <div class="task-card">
            <div class="task-header">
                <span class="priority" style="background:{color}">{task['priority']}</span>
                <span class="title">{task['title']}</span>
                {completed_html}
            </div>
            {info_html}
        </div>'''
    
    return cards

def render_tasks_view(tasks: dict) -> str:
    """Render the full tasks board."""
    columns = [
        ('doing', '🔨', 'In Progress', '#ef4444'),
        ('open', '📥', 'Open', '#22c55e'),
        ('review', '👀', 'Review', '#eab308'),
        ('blocked-joe', '🧑', 'Blocked (Joe)', '#f97316'),
        ('blocked-owen', '🤖', 'Blocked (Owen)', '#6b7280'),
        ('done', '✅', 'Done', '#22c55e'),
    ]
    
    columns_html = ''
    for state, icon, label, border_color in columns:
        count = len(tasks[state])
        limit = 15 if state == 'done' else None
        task_list = tasks[state][:limit] if limit else tasks[state]
        content = render_task_cards(task_list, state) if task_list else '<div class="empty">Empty</div>'
        
        columns_html += f'''
        <div class="column" style="border-top: 3px solid {border_color}">
            <div class="column-header">
                {icon} {label}
                <span class="count">{count}</span>
            </div>
            {content}
        </div>'''
    
    return f'<div class="columns">{columns_html}</div>'

def render_logs_view(logs: list) -> str:
    """Render the logs view."""
    if not logs:
        return '<div class="empty">No logs found</div>'
    
    entries_html = ''
    for entry in logs:
        ts = entry.get('timestamp', '')
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            time_str = dt.strftime('%m/%d %H:%M:%S')
        except:
            time_str = ts[:19] if ts else 'unknown'
        
        action_id = entry.get('action_id', 'unknown')
        reason = entry.get('reason', '')
        category = entry.get('category', 'unknown')
        
        # Color code by category
        cat_colors = {
            'active_work': '#ef4444',
            'task_queue': '#22c55e',
            'communication': '#3b82f6',
            'review': '#eab308',
            'generation': '#8b5cf6',
        }
        cat_color = cat_colors.get(category, '#64748b')
        
        entries_html += f'''
        <div class="log-entry">
            <span class="log-time">{time_str}</span>
            <div class="log-action">
                <span class="log-action-id">{action_id}</span>
                <span class="log-reason">{reason[:50]}{'...' if len(reason) > 50 else ''}</span>
            </div>
            <span class="log-category" style="border-color: {cat_color}; color: {cat_color}">{category}</span>
        </div>'''
    
    return f'''
    <div class="section">
        <div class="section-title">📜 Recent Heartbeat Cycles</div>
        <div class="log-list">{entries_html}</div>
    </div>
    '''

def render_timeline_view(logs: list, tasks: dict) -> str:
    """Render a combined timeline of logs and completed tasks."""
    events = []
    
    # Add log entries
    for entry in logs:
        ts = entry.get('timestamp', '')
        events.append({
            'type': 'heartbeat',
            'timestamp': ts,
            'action': entry.get('action_id', 'unknown'),
            'reason': entry.get('reason', ''),
        })
    
    # Add completed tasks (today only)
    today = datetime.now().strftime('%Y-%m-%d')
    for task in tasks.get('done', []):
        if task.get('completed') and today in task.get('completed', ''):
            events.append({
                'type': 'task',
                'timestamp': task['mtime'],
                'title': task['title'],
                'priority': task['priority'],
            })
    
    # Sort by timestamp
    events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    items_html = ''
    for event in events[:30]:
        ts = event.get('timestamp', '')
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            time_str = dt.strftime('%H:%M:%S')
        except:
            time_str = ts[:8] if ts else ''
        
        if event['type'] == 'task':
            items_html += f'''
            <div class="timeline-item task">
                <div class="timeline-time">{time_str}</div>
                <div class="timeline-content">
                    ✅ Completed: <strong>{event['title']}</strong>
                </div>
            </div>'''
        else:
            items_html += f'''
            <div class="timeline-item heartbeat">
                <div class="timeline-time">{time_str}</div>
                <div class="timeline-content">
                    💓 {event['action']}: {event['reason'][:60]}
                </div>
            </div>'''
    
    return f'''
    <div class="section">
        <div class="section-title">⏱️ Activity Timeline (Today)</div>
        <div class="timeline">{items_html}</div>
    </div>
    '''

# ─────────────────────────────────────────────────────────────────────────────
# HTTP Handler
# ─────────────────────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    workspace = DEFAULT_WORKSPACE
    
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        view = params.get('view', ['overview'])[0]
        
        html = render_dashboard(self.workspace, view)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        pass  # Silence logs

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Owen Dashboard Server')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to listen on')
    parser.add_argument('--workspace', type=Path, default=DEFAULT_WORKSPACE, help='Workspace path')
    args = parser.parse_args()
    
    DashboardHandler.workspace = args.workspace
    
    print(f"🦉 Owen Dashboard running at http://localhost:{args.port}")
    print(f"   Workspace: {args.workspace}")
    HTTPServer(('0.0.0.0', args.port), DashboardHandler).serve_forever()

if __name__ == '__main__':
    main()
