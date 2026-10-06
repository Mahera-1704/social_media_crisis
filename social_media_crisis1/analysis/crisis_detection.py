"""Crisis score, keyword stats and alert creation (no Flask code here)."""
import math
from datetime import timedelta
from models import db, Alert, Keyword, SocialPost, get_setting
from .sentiment import clean_text, analyze_sentiment

def find_keywords(clean):
    return [k for k in Keyword.query.filter_by(active=True)
            if f" {k.keyword.lower()} " in f" {clean} "]

def score_post(sent, kws, eng):
    """Weighted 0-100 score. Weights come from Settings and are normalised."""
    w = [float(get_setting(n)) for n in ("w_sentiment", "w_keywords", "w_engagement")]
    neg = max(0, -sent) * 100                                   # negative sentiment
    kw = min(100, sum(k.severity for k in kws) * 35)            # crisis keywords
    eng_s = min(100, math.log1p(eng) / math.log1p(1000) * 100)  # engagement
    eng_s *= neg / 100          # engagement only amplifies NEGATIVE posts
    return round((neg * w[0] + kw * w[1] + eng_s * w[2]) / sum(w), 1)

def status_for(score):
    if score >= float(get_setting("critical_threshold")): return "CRITICAL"
    if score >= float(get_setting("warning_threshold")): return "WARNING"
    return "NORMAL"

def create_post(platform, username, text, likes=0, shares=0, comments=0, ts=None):
    """Clean, analyse and store one post. Returns False if empty/duplicate."""
    text = (text or "").strip()
    clean = clean_text(text)
    if not clean:
        return False
    if SocialPost.query.filter_by(platform=platform, username=username, clean_text=clean).first():
        return False
    label, s = analyze_sentiment(clean)
    kws = find_keywords(clean)
    p = SocialPost(platform=platform, username=username, post_text=text, clean_text=clean,
                   likes=likes, shares=shares, comments=comments, sentiment=label,
                   sentiment_score=s, created_at=ts)
    if ts is None:
        from datetime import datetime; p.created_at = datetime.utcnow()
    p.crisis_score = score_post(s, kws, p.engagement)
    db.session.add(p)
    return True

def keyword_stats(posts):
    rows = []
    for k in Keyword.query.filter_by(active=True):
        m = [p for p in posts if f" {k.keyword.lower()} " in f" {p.clean_text} "]
        if m:
            rows.append(dict(keyword=k.keyword, freq=len(m), severity=k.severity,
                             neg=sum(p.sentiment == "Negative" for p in m)))
    return sorted(rows, key=lambda r: -r["freq"])

def window_score():
    """Compares the latest 24h of data with the 24h before it (spike detection)."""
    last = db.session.query(db.func.max(SocialPost.created_at)).scalar()
    if not last:
        return dict(score=0, cur=[], old=[])
    cut = last - timedelta(hours=24)
    cur = SocialPost.query.filter(SocialPost.created_at > cut).all()
    old = SocialPost.query.filter(SocialPost.created_at > cut - timedelta(hours=24),
                                  SocialPost.created_at <= cut).all()
    avg = sum(p.crisis_score for p in cur) / len(cur)
    spike = min(100, max(0, len(cur) / len(old) - 1) * 50) if old else 0
    ws = float(get_setting("w_spike")) / 100
    return dict(score=round((1 - ws) * avg + ws * spike, 1), cur=cur, old=old)

def _add_alert(sev, typ, msg, score):
    if not Alert.query.filter(Alert.message == msg, Alert.status != "Resolved").first():
        db.session.add(Alert(alert_type=typ, severity=sev, message=msg, crisis_score=score))

def run_detection():
    """Creates alerts when signals suggest a POTENTIAL crisis (needs human review)."""
    w = window_score(); cur, old, sc = w["cur"], w["old"], w["score"]
    if not cur:
        return
    st = status_for(sc)
    neg = lambda ps: sum(p.sentiment == "Negative" for p in ps)
    if st != "NORMAL":
        _add_alert(st, "Negative activity",
                   f"Potential crisis indicators: {neg(cur)} negative posts in the latest 24h "
                   f"(previous 24h: {neg(old)}). Human review required.", sc)
    stats = keyword_stats(cur)
    if stats and stats[0]["freq"] >= 3:
        _add_alert("WARNING", "Keyword spike",
                   f"High frequency of '{stats[0]['keyword']}' ({stats[0]['freq']} posts) "
                   f"in the latest 24h. Human review required.", sc)
    db.session.commit()
