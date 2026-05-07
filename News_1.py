from flask import Flask, request, jsonify, send_file
import urllib.request
import urllib.parse
import json
import os
import re
from collections import defaultdict

app = Flask(__name__, template_folder="templates")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── API Keys ──────────────────────────────────────────
GNEWS_API_KEY = "fdd48629b42385245663a6501e92b23f"
YOUTUBE_API_KEY = "AIzaSyDEe7Xby_6tXhMuEo-29YwzaEfCmBv0d9E"
AK = os.environ.get("ANTHROPIC_API_KEY", "")

# ── HTTP helper ───────────────────────────────────────


def _req(url, data=None, headers={}):
    req = urllib.request.Request(url, data, headers)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

# ── News ──────────────────────────────────────────────


def fetch_news(topic=""):
    try:
        q = urllib.parse.quote(topic) if topic else "news"
        url = f"https://gnews.io/api/v4/search?q={q}&lang=en&max=25&apikey={GNEWS_API_KEY}"
        data = _req(url)
        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title":       a.get("title", "")[:140],
                "source":      (a.get("source") or {}).get("name", ""),
                "description": re.sub(r"\s+", " ", a.get("description", ""))[:500],
                "url":         a.get("url", "#"),
                "image":       a.get("image", ""),
                "pubDate":     (a.get("publishedAt", ""))[:10]
            })
        return articles
    except Exception as e:
        print("GNews err:", e)
        return []

# ── YouTube ───────────────────────────────────────────


def fetch_youtube_video(headline):
    try:
        q = urllib.parse.quote(headline[:100])
        url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet"
            f"&q={q}"
            f"&type=video"
            f"&maxResults=1"
            f"&relevanceLanguage=en"
            f"&key={YOUTUBE_API_KEY}"
        )
        data = _req(url)
        items = data.get("items", [])
        if items:
            item = items[0]
            return {
                "video_id": item["id"]["videoId"],
                "title":    item["snippet"]["title"],
                "thumb":    item["snippet"]["thumbnails"]["medium"]["url"]
            }
        return None
    except Exception as e:
        print("YouTube err:", e)
        return None

# ── Claude Detail ─────────────────────────────────────


def generate_detail(title, desc, url):
    prompt = f"""You are a professional news analyst. Analyze this article and write a deep analysis in exactly this structure:

**What Happened**
2-3 sentences explaining the core event clearly.

**Key People & Reactions**
Who is involved and how have they responded.

**Why It Matters**
The broader significance and implications.

**What Comes Next**
Likely developments or things to watch.

TITLE: {title}
ARTICLE: {desc[:800]}
SOURCE URL: {url}

Write in plain flowing prose under each heading. No bullet points. Be insightful, not just descriptive."""

    try:
        body = json.dumps({
            "model":      "claude-haiku-4-5-20251001",
            "max_tokens": 600,
            "messages":   [{"role": "user", "content": prompt}]
        }).encode()

        headers = {
            "Content-Type":      "application/json",
            "x-api-key":         AK,
            "anthropic-version": "2023-06-01"
        }

        response = _req(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers=headers
        )
        return response["content"][0]["text"].strip()

    except Exception as e:
        print("Claude err:", e)
        return None


# ── Sentiment ─────────────────────────────────────────
POS = {"good", "great", "win", "success", "growth", "rise", "gain", "improve", "hope", "strong",
       "record", "boost", "safe", "breakthrough", "peace", "recovery", "profit", "award"}
NEG = {"bad", "crisis", "war", "attack", "death", "fail", "crash", "loss", "fear", "danger",
       "worst", "decline", "flood", "fire", "arrested", "killed", "threat", "collapse", "scandal", "fraud"}


def sentiment(text):
    words = set(re.findall(r'\b\w+\b', text.lower()))
    p, n = len(words & POS), len(words & NEG)
    if p > n:
        return "Positive"
    elif n > p:
        return "Negative"
    return "Neutral"


# ── Grouping ──────────────────────────────────────────
CATEGORIES = {
    "Technology":    ["tech", "ai", "software", "robot", "google", "microsoft", "apple"],
    "Economy":       ["market", "stock", "inflation", "trade", "bank", "crypto"],
    "Health":        ["health", "covid", "vaccine", "hospital", "medicine"],
    "Politics":      ["election", "government", "minister", "policy", "war"],
    "Sports":        ["football", "soccer", "tennis", "league", "match"],
    "Entertainment": ["movie", "music", "celebrity", "netflix", "film"]
}


def group_articles(articles):
    groups = {k: [] for k in CATEGORIES}
    groups["General"] = []
    for a in articles:
        text = (a["title"] + " " + a["description"]).lower()
        assigned = False
        for cat, keywords in CATEGORIES.items():
            if any(k in text for k in keywords):
                groups[cat].append(a)
                assigned = True
        if not assigned:
            groups["General"].append(a)
    return {k: v for k, v in groups.items() if v}

# ── Routes ────────────────────────────────────────────


@app.route("/")
@app.route("/news.html")
def index():
    return send_file(os.path.join(BASE_DIR, "templates", "News.html"))


@app.route("/api/news")
def api_news():
    topic = request.args.get("topic", "").strip()
    articles = fetch_news(topic)
    for a in articles:
        a["sentiment"] = sentiment(a["title"] + a["description"])
    grouped = group_articles(articles)
    return jsonify({
        "groups": grouped,
        "meta": {
            "topic": topic or "Trending",
            "total": len(articles)
        }
    })


@app.route("/api/youtube")
def api_youtube():
    headline = request.args.get("q", "").strip()
    if not headline:
        return jsonify({"error": "no query"}), 400
    result = fetch_youtube_video(headline)
    if result:
        return jsonify(result)
    return jsonify({"video_id": None})


@app.route("/api/detail")
def api_detail():
    title = request.args.get("title", "").strip()
    desc = request.args.get("desc",  "").strip()
    url = request.args.get("url",   "").strip()
    if not title:
        return jsonify({"error": "no title"}), 400
    result = generate_detail(title, desc, url)
    if result:
        return jsonify({"detailed": result})
    return jsonify({"detailed": desc})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
