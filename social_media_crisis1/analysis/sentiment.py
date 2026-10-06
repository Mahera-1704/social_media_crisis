"""Text cleaning + sentiment. Replace analyze_sentiment() later with an ML model."""
import re
from textblob import TextBlob

def clean_text(text):
    t = text.lower()
    t = re.sub(r"https?://\S+|www\.\S+", "", t)   # remove URLs
    t = re.sub(r"@\w+", "", t)                     # remove mentions
    t = t.replace("#", "")                         # keep hashtag word
    t = re.sub(r"[^a-z0-9\s]", " ", t)             # remove symbols/emojis
    return re.sub(r"\s+", " ", t).strip()          # normalise spaces

def analyze_sentiment(text):
    """Returns (label, score) with score between -1 and +1."""
    score = round(TextBlob(text).sentiment.polarity, 2)
    label = "Positive" if score >= 0.1 else "Negative" if score <= -0.1 else "Neutral"
    return label, score
