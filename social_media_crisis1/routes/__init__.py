"""All web routes. Heavy logic lives in analysis/."""
import json
from datetime import datetime, timedelta
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from sqlalchemy.exc import SQLAlchemyError
from models import db, User, SocialPost, Keyword, Alert, get_setting, set_setting
from analysis.crisis_detection import (create_post, keyword_stats, window_score,
                                       status_for, run_detection)

bp = Blueprint("main", __name__)
PLATFORMS = ["X", "Facebook", "Instagram", "YouTube", "Other"]
SENTS = ["Positive", "Neutral", "Negative"]

def pdate(s, fmt="%Y-%m-%d"):
    try: return datetime.strptime(s, fmt)
    except (TypeError, ValueError): return None

def to_int(v):
    try: return max(0, int(float(v)))
    except (TypeError, ValueError): return 0

# ---------- Auth ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if u and check_password_hash(u.password_hash, request.form.get("password", "")):
            login_user(u)
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))

# ---------- Dashboard ----------
@bp.route("/")
@login_required
def dashboard():
    w = window_score()
    return render_template("dashboard.html",
        total=SocialPost.query.count(),
        counts={s: SocialPost.query.filter_by(sentiment=s).count() for s in SENTS},
        critical=Alert.query.filter_by(severity="CRITICAL").filter(Alert.status != "Resolved").count(),
        score=w["score"], status=status_for(w["score"]),
        alerts=Alert.query.order_by(Alert.created_at.desc()).limit(5).all())

# ---------- Chart data API (real DB data, filtered by date range) ----------
@bp.route("/api/data")
@login_required
def api_data():
    last = db.session.query(db.func.max(SocialPost.created_at)).scalar() or datetime.utcnow()
    days = request.args.get("days", "7")
    if days == "custom":
        start = pdate(request.args.get("start")) or last - timedelta(days=7)
        end = (pdate(request.args.get("end")) or last) + timedelta(days=1)
    else:  # ranges are anchored to the newest post so demo data always shows
        start, end = last - timedelta(days=to_int(days) or 7), last + timedelta(seconds=1)
    posts = SocialPost.query.filter(SocialPost.created_at >= start, SocialPost.created_at <= end).all()
    empty = dict(labels=[], sent={s: [] for s in SENTS}, volume=[], crisis=[], totals={},
                 platforms=[], engagement={}, keywords=[], top_negative=[], total_eng=0, avg_eng=0)
    if not posts:
        return jsonify(empty)
    df = pd.DataFrame([dict(platform=p.platform, username=p.username, text=p.post_text,
                            sentiment=p.sentiment, score=p.crisis_score, eng=p.engagement,
                            t=p.created_at) for p in posts])
    fmt = "%Y-%m-%d %H:00" if (end - start) <= timedelta(days=1, seconds=1) else "%Y-%m-%d"
    df["bucket"] = df.t.dt.strftime(fmt)
    tr = df.groupby(["bucket", "sentiment"]).size().unstack(fill_value=0).reindex(columns=SENTS, fill_value=0)
    plat = df.groupby(["platform", "sentiment"]).size().unstack(fill_value=0).reindex(columns=SENTS, fill_value=0)
    plat["Posts"] = plat.sum(axis=1)
    top = df[df.sentiment == "Negative"].nlargest(5, "score")[["platform", "username", "text", "eng", "score"]]
    return jsonify(labels=list(tr.index), sent={s: tr[s].tolist() for s in SENTS},
        volume=df.groupby("bucket").size().tolist(),
        crisis=df.groupby("bucket").score.mean().round(1).tolist(),
        totals={k: int(v) for k, v in df.sentiment.value_counts().items()},
        platforms=json.loads(plat.reset_index().to_json(orient="records")),
        engagement={k: int(v) for k, v in df.groupby("platform").eng.sum().items()},
        keywords=keyword_stats(posts)[:10],
        top_negative=json.loads(top.to_json(orient="records")),
        total_eng=int(df.eng.sum()), avg_eng=round(float(df.eng.mean()), 1))

@bp.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")

# ---------- Posts ----------
@bp.route("/posts")
@login_required
def posts():
    a, q = request.args, SocialPost.query
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.filter(db.or_(SocialPost.post_text.ilike(like), SocialPost.username.ilike(like)))
    if a.get("platform"): q = q.filter_by(platform=a["platform"])
    if a.get("sentiment"): q = q.filter_by(sentiment=a["sentiment"])
    warn, crit = float(get_setting("warning_threshold")), float(get_setting("critical_threshold"))
    sev = a.get("severity")
    if sev == "CRITICAL": q = q.filter(SocialPost.crisis_score >= crit)
    elif sev == "WARNING": q = q.filter(SocialPost.crisis_score >= warn, SocialPost.crisis_score < crit)
    elif sev == "NORMAL": q = q.filter(SocialPost.crisis_score < warn)
    d = pdate(a.get("date"))
    if d: q = q.filter(SocialPost.created_at >= d, SocialPost.created_at < d + timedelta(days=1))
    page = q.order_by(SocialPost.created_at.desc()).paginate(
        page=a.get("page", 1, type=int), per_page=15, error_out=False)
    return render_template("posts.html", page=page, platforms=PLATFORMS, sents=SENTS,
                           status_for=status_for)

@bp.route("/posts/add", methods=["POST"])
@login_required
def add_post():
    f = request.form
    if f.get("platform") not in PLATFORMS or not f.get("post_text", "").strip() or not f.get("username", "").strip():
        flash("Platform, username and post text are required.", "danger")
        return redirect(url_for("main.posts"))
    ts = pdate(f.get("timestamp"), "%Y-%m-%dT%H:%M")
    try:
        ok = create_post(f["platform"], f["username"].strip(), f["post_text"], to_int(f.get("likes")),
                         to_int(f.get("shares")), to_int(f.get("comments")), ts)
        db.session.commit()
        if ok: run_detection()
        flash("Post added." if ok else "Post is empty or a duplicate.", "success" if ok else "warning")
    except SQLAlchemyError:
        db.session.rollback(); flash("Database error. Please try again.", "danger")
    return redirect(url_for("main.posts"))

@bp.route("/posts/<int:pid>/delete", methods=["POST"])
@login_required
def delete_post(pid):
    p = db.session.get(SocialPost, pid)
    if p:
        db.session.delete(p); db.session.commit(); flash("Post deleted.", "success")
    return redirect(url_for("main.posts"))

@bp.route("/posts/import", methods=["POST"])
@login_required
def import_csv():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Please upload a valid .csv file.", "danger"); return redirect(url_for("main.posts"))
    need = {"platform", "username", "post_text", "likes", "shares", "comments", "timestamp"}
    try:
        df = pd.read_csv(f)
    except Exception:
        flash("Could not read the file. Is it a valid CSV?", "danger"); return redirect(url_for("main.posts"))
    df.columns = [c.strip().lower() for c in df.columns]
    if not need.issubset(df.columns):
        flash("Invalid CSV. Missing columns: " + ", ".join(sorted(need - set(df.columns))), "danger")
        return redirect(url_for("main.posts"))
    added = skipped = 0
    try:
        for r in df.itertuples():
            ts = pd.to_datetime(r.timestamp, errors="coerce")
            plat = str(r.platform).strip()
            ok = create_post(plat if plat in PLATFORMS else "Other", str(r.username).strip(),
                             "" if pd.isna(r.post_text) else str(r.post_text), to_int(r.likes),
                             to_int(r.shares), to_int(r.comments), None if pd.isna(ts) else ts.to_pydatetime())
            added += ok; skipped += not ok
        db.session.commit(); run_detection()
        flash(f"Imported {added} posts. Skipped {skipped} empty/duplicate rows.", "success")
    except SQLAlchemyError:
        db.session.rollback(); flash("Database error during import.", "danger")
    return redirect(url_for("main.posts"))

# ---------- Alerts ----------
@bp.route("/alerts")
@login_required
def alerts():
    return render_template("alerts.html", alerts=Alert.query.order_by(Alert.created_at.desc()).all())

@bp.route("/alerts/<int:aid>/status", methods=["POST"])
@login_required
def alert_status(aid):
    a, s = db.session.get(Alert, aid), request.form.get("status")
    if a and s in ("New", "Reviewing", "Resolved"):
        a.status = s; db.session.commit(); flash(f"Alert #{aid} marked {s}.", "success")
    return redirect(url_for("main.alerts"))

# ---------- Keywords ----------
@bp.route("/keywords")
@login_required
def keywords():
    stats = {r["keyword"]: r for r in keyword_stats(SocialPost.query.all())}
    return render_template("keywords.html", kws=Keyword.query.order_by(Keyword.keyword).all(), stats=stats)

@bp.route("/keywords/add", methods=["POST"])
@login_required
def add_keyword():
    k = request.form.get("keyword", "").strip().lower()
    if not k or Keyword.query.filter_by(keyword=k).first():
        flash("Enter a new, non-empty keyword.", "danger")
    else:
        db.session.add(Keyword(keyword=k, severity=min(3, max(1, to_int(request.form.get("severity", 1))))))
        db.session.commit(); flash("Keyword added.", "success")
    return redirect(url_for("main.keywords"))

@bp.route("/keywords/<int:kid>/edit", methods=["POST"])
@login_required
def edit_keyword(kid):
    k, new = db.session.get(Keyword, kid), request.form.get("keyword", "").strip().lower()
    dup = Keyword.query.filter(Keyword.keyword == new, Keyword.id != kid).first()
    if not k or not new or dup:
        flash("Invalid or duplicate keyword.", "danger")
    else:
        k.keyword, k.active = new, bool(request.form.get("active"))
        k.severity = min(3, max(1, to_int(request.form.get("severity", 1))))
        db.session.commit(); flash("Keyword updated.", "success")
    return redirect(url_for("main.keywords"))

@bp.route("/keywords/<int:kid>/delete", methods=["POST"])
@login_required
def delete_keyword(kid):
    k = db.session.get(Keyword, kid)
    if k: db.session.delete(k); db.session.commit(); flash("Keyword deleted.", "success")
    return redirect(url_for("main.keywords"))

# ---------- Settings ----------
FIELDS = [("warning_threshold", "Warning threshold (0-100)"), ("critical_threshold", "Critical threshold (0-100)"),
          ("w_sentiment", "Weight: negative sentiment"), ("w_keywords", "Weight: crisis keywords"),
          ("w_spike", "Weight: activity spike"), ("w_engagement", "Weight: engagement"),
          ("refresh_seconds", "Dashboard refresh interval (seconds, min 5)")]

@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        try:
            v = {n: float(request.form[n]) for n, _ in FIELDS}
            assert all(0 <= v[n] <= 100 for n, _ in FIELDS[:6]) and v["refresh_seconds"] >= 5
            assert v["warning_threshold"] < v["critical_threshold"] and v["w_sentiment"] + v["w_keywords"] + v["w_engagement"] > 0
        except (ValueError, KeyError, AssertionError):
            flash("Invalid settings: values must be numbers, weights 0-100, warning below critical.", "danger")
            return redirect(url_for("main.settings"))
        for n, val in v.items(): set_setting(n, val)
        db.session.commit(); flash("Settings saved.", "success")
        return redirect(url_for("main.settings"))
    return render_template("settings.html", fields=[(n, l, get_setting(n)) for n, l in FIELDS])
