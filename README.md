# Crictalx Polls

A premium dark-themed cricket poll app built with Flask, SQLAlchemy, Tailwind (CDN), and vanilla JS.

## Features
- Admin-managed fixtures and squads
- Auto-generated poll options from team rosters
- Manual result entry and points calculation
- User profile with avatar upload and points chart
- Admin panel for manual overrides
- Live voting progress bars with glowing UI

## Setup

1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set environment variables (optional):

```bash
set SECRET_KEY=your-secret
set ADMIN_USERNAME=admin
set ADMIN_PASSWORD=admin123
```

4. Run the app:

```bash
python app.py
```

Visit http://127.0.0.1:5000/login

## Default Users
- Admin: admin / admin123
- Demo user: player1 / player123

## Notes
- The app seeds sample data on first run.
- Admins manage team rosters and matches from the Admin Panel.
- Poll options can be sourced from Team A/Team B batsmen, bowlers, all rounders, or all players.
- Avatars are uploaded from the Profile page and stored in static/uploads/avatars.
- If you use a .env file, keep it local and out of source control.
