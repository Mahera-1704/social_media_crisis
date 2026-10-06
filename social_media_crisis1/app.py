"""Entry point: python app.py"""
import os, secrets
from datetime import datetime
from flask import Flask, session, request, abort, render_template
from flask_login import LoginManager
from werkzeug.security import generate_password_hash
from config import Config, BASE
from models import db, User, Keyword, Setting, DEFAULTS, get_setting

COLORS = {"CRITICAL": "danger", "WARNING": "warning", "NORMAL": "success", "Negative": "danger",
          "Positive": "success", "Neutral": "secondary", "New": "danger", "Reviewing": "warning",
          "Resolved": "success"}
SEED_KEYWORDS = {"scam": 3, "fraud": 3, "fake": 2, "refund": 2, "complaint": 2, "unsafe": 3,
                 "danger": 3, "terrible": 2, "worst": 2, "angry": 2, "cheating": 3, "problem": 1,
                 "issue": 1, "failure": 2, "hack": 3, "leak": 3, "boycott": 3, "lawsuit": 3}

def ago(dt):
    m = int((datetime.utcnow() - dt).total_seconds() // 60)
    return f"{m} min ago" if m < 60 else f"{m // 60} h ago" if m < 1440 else f"{m // 1440} d ago"

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(os.path.join(BASE, "database"), exist_ok=True)
    db.init_app(app)
    lm = LoginManager(app); lm.login_view = "main.login"
    lm.user_loader(lambda uid: db.session.get(User, int(uid)))
    app.jinja_env.filters["color"] = lambda s: COLORS.get(s, "secondary")
    app.jinja_env.filters["ago"] = ago

    @app.before_request
    def csrf_check():  # simple CSRF protection for every POST
        if request.method == "POST" and (not session.get("_csrf") or request.form.get("_csrf") != session["_csrf"]):
            abort(400)

    @app.context_processor
    def inject():
        session.setdefault("_csrf", secrets.token_hex(16))
        try: refresh = get_setting("refresh_seconds")
        except Exception: refresh = DEFAULTS["refresh_seconds"]
        return {"csrf": session["_csrf"], "refresh": int(float(refresh))}

    for code, msg in {400: "Bad request or expired form. Please go back and retry.", 404: "Page not found.",
                      413: "File too large (max 2 MB).", 500: "Something went wrong on our side."}.items():
        app.register_error_handler(code, lambda e, msg=msg: (render_template("error.html", msg=msg), e.code if hasattr(e, "code") else 500))

    from routes import bp
    app.register_blueprint(bp)

    with app.app_context():  # database initialisation + seed data
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            db.session.add(User(username="admin", password_hash=generate_password_hash("admin123")))
        if Keyword.query.count() == 0:  # seed default keywords once
            for k, s in SEED_KEYWORDS.items():
                db.session.add(Keyword(keyword=k, severity=s))
        for n, v in DEFAULTS.items():
            if not Setting.query.filter_by(setting_name=n).first():
                db.session.add(Setting(setting_name=n, setting_value=v))
        db.session.commit()
    return app

app = create_app()
if __name__ == "__main__":
    app.run(debug=False)
