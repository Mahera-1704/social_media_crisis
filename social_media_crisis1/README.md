# Social Media Crisis Monitoring System
Flask web app that imports social posts (manual or CSV), scores sentiment/keywords/engagement, detects unusual negative activity and shows it on an admin dashboard. It flags **potential** crises for human review only.

**Stack:** Flask, Flask-SQLAlchemy, Flask-Login, SQLite, Pandas, TextBlob, Bootstrap 5, Chart.js.

## Install and run (Windows)
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 (database is created automatically on first run).

## Default login
`admin` / `admin123`  **WARNING: development password. Change it before any deployment** (and set a SECRET_KEY environment variable).

## Using it
Log in, go to **Social Posts**, import `data/sample_posts.csv` (fictional demo data), then explore Dashboard, Analytics, Keywords, Alerts and Settings.

## CSV format
`platform,username,post_text,likes,shares,comments,timestamp` (platform: X, Facebook, Instagram, YouTube, Other).

## Architecture
Routes (`routes/`) -> analysis (`analysis/sentiment.py`, `analysis/crisis_detection.py`) -> models/SQLite (`models/`).
Crisis score per post = weighted negative sentiment + keyword severity + engagement (engagement counts only for negative posts). Window score blends the average with a 24h-vs-previous-24h volume spike. Weights and thresholds are editable in Settings.

## Screenshots
(add screenshots here)

## Future enhancements
ML sentiment model, live X/YouTube APIs, email alerts, multi-user roles, password change page, topic clustering.
