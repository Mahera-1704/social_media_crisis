"""All database models (SQLAlchemy ORM)."""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# Default settings; the admin can change them on the Settings page.
DEFAULTS = {"warning_threshold": "25", "critical_threshold": "45",
            "w_sentiment": "40", "w_keywords": "25", "w_spike": "20",
            "w_engagement": "15", "refresh_seconds": "30"}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SocialPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(20), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    post_text = db.Column(db.Text, nullable=False)
    clean_text = db.Column(db.Text)
    likes = db.Column(db.Integer, default=0)
    shares = db.Column(db.Integer, default=0)
    comments = db.Column(db.Integer, default=0)
    sentiment = db.Column(db.String(10))
    sentiment_score = db.Column(db.Float)
    crisis_score = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def engagement(self):
        return (self.likes or 0) + (self.shares or 0) + (self.comments or 0)

class Keyword(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(60), unique=True, nullable=False)
    severity = db.Column(db.Integer, default=1)  # 1 low, 2 medium, 3 high
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50))
    severity = db.Column(db.String(10))  # WARNING / CRITICAL
    message = db.Column(db.String(300))
    crisis_score = db.Column(db.Float)
    status = db.Column(db.String(10), default="New")  # New / Reviewing / Resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setting_name = db.Column(db.String(50), unique=True, nullable=False)
    setting_value = db.Column(db.String(100))

def get_setting(name):
    s = Setting.query.filter_by(setting_name=name).first()
    return s.setting_value if s else DEFAULTS[name]

def set_setting(name, value):
    s = Setting.query.filter_by(setting_name=name).first()
    if s: s.setting_value = str(value)
    else: db.session.add(Setting(setting_name=name, setting_value=str(value)))
