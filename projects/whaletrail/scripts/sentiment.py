#!/usr/bin/env python3
"""WhaleTrail Sentiment — X/Twitter gold KOL sentiment scoring via Ollama.

Fetches latest tweets from gold KOLs, scores each with Ollama qwen3:4b,
aggregates into a daily gold sentiment index.

Usage:
  python scripts/sentiment.py                        # scan all gold KOLs
  python scripts/sentiment.py --account PeterLBrandt # single account

Requires: TWITTER_BEARER_TOKEN env var
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Config ───────────────────────────────────────────────────────
BEARER_TOKEN = os.environ.get(
    "TWITTER_BEARER_TOKEN",
    "AAAAAAAAAAAAAAAAAAAAADgc%2FAEAAAAAD9qWDxYIkEWNKx1ZJgdjh0hcaOM%3DiWf0oM3TXl0JStLtXWP5ay2QIG3xEJoC7WCrcrEXEFVuDnRzwm",
)
OLLAMA_MODEL = "qwen3:4b"
OLLAMA_BIN = "/opt/homebrew/bin/ollama"
RESULTS_DIR = ROOT / "results"
STATE_FILE = RESULTS_DIR / "sentiment_state.json"
PROXY = os.environ.get("HTTPS_PROXY", "http://127.0.0.1:7890")

os.environ.setdefault("HTTPS_PROXY", PROXY)

# Gold KOLs from WHALE_WATCH.md section 1
GOLD_KOLS = [
    "PeterLBrandt", "LukeGromen", "SantiagoAuFund", "KitcoNewsNOW",
    "GoldPredictors", "KobeissiLetter", "DonDurrett", "TheDailyGold",
    "badcharts1", "KimbleCharting", "GoldSilver_com", "TheGoldAdvisor",
    "Oliver_MSA", "GoldCore", "spotgoldprice", "goldminingnews",
    "SWGoldReport", "Huanusa",
]

SCORING_PROMPT = (
    "Classify gold sentiment: {tweet}\n"
    "Reply one line: SCORE: bullish|bearish|neutral CONFIDENCE: 1-5"
)


# ── X API helpers ────────────────────────────────────────────────
def x_get(path: str) -> dict:
    """Make an X API v2 GET request."""
    url = f"https://api.x.com{path}"
    req = Request(url, headers={"Authorization": f"Bearer {BEARER_TOKEN}"})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠️ X API error: {e}")
        return {}


def get_user_id(username: str, cache: dict) -> Optional[str]:
    """Resolve username → user ID, with local cache."""
    if username in cache:
        return cache[username]
    data = x_get(f"/2/users/by/username/{username}")
    uid = data.get("data", {}).get("id")
    if uid:
        cache[username] = uid
    return uid


def get_recent_tweets(user_id: str, count: int = 5) -> list[dict]:
    """Fetch latest tweets for a user."""
    data = x_get(
        f"/2/users/{user_id}/tweets"
        f"?max_results={count}&tweet.fields=created_at,text"
        f"&exclude=retweets,replies"
    )
    return data.get("data", [])


# ── Ollama scoring ───────────────────────────────────────────────
def score_tweet(text: str) -> dict:
    """Send a tweet to Ollama for sentiment scoring."""
    prompt = SCORING_PROMPT.format(tweet=text[:500])

    result = subprocess.run(
        [OLLAMA_BIN, "run", OLLAMA_MODEL, prompt],
        capture_output=True, text=True, timeout=180,
        env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "HOME": str(Path.home())},
    )
    raw = (result.stdout + result.stderr).strip()
    # Clean ANSI/spinners/thinking
    raw = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", raw)
    raw = re.sub(r"[⠙⠹⠸⠼⠴⠦⠧⠇⠏⠋]", "", raw)
    raw = re.sub(r"Thinking[\s\S]*?done thinking\.", "", raw, flags=re.DOTALL)
    raw = raw.strip()

    # Parse response
    score_match = re.search(r"SCORE:\s*(bullish|bearish|neutral)", raw, re.IGNORECASE)
    conf_match = re.search(r"CONFIDENCE:\s*(\d)", raw)
    kw_match = re.search(r"KEYWORD:\s*(\S+)", raw, re.IGNORECASE)

    return {
        "score": score_match.group(1).lower() if score_match else "neutral",
        "confidence": int(conf_match.group(1)) if conf_match else 3,
        "keyword": kw_match.group(1).lower() if kw_match else "general",
        "raw": raw[:200],
    }


# ── Main ─────────────────────────────────────────────────────────
def scan(args) -> dict:
    """Scan gold KOLs and return sentiment report."""
    # Load state
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass

    user_cache = state.get("user_cache", {})
    seen_tweets = set(state.get("seen_tweets", []))
    today = date.today().isoformat()

    # Filter KOLs if --account specified
    kols = [args.account] if args.account else GOLD_KOLS

    entries = []
    scores = {"bullish": 0, "bearish": 0, "neutral": 0}

    for username in kols:
        print(f"\n🔍 @{username} …", end=" ", flush=True)
        uid = get_user_id(username, user_cache)
        if not uid:
            print("no user ID")
            continue

        tweets = get_recent_tweets(uid, count=5)
        if not tweets:
            print("no tweets")
            continue

        print(f"{len(tweets)} tweets")
        for tw in tweets:
            tid = tw["id"]
            if tid in seen_tweets:
                continue
            seen_tweets.add(tid)

            s = score_tweet(tw["text"])
            s["account"] = f"@{username}"
            s["tweet_id"] = tid
            s["tweet_text"] = tw["text"]  # full text
            s["created_at"] = tw.get("created_at", "")
            entries.append(s)
            scores[s["score"]] += 1

            emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➖"}[s["score"]]
            print(f"  {emoji} {s['score']} c={s['confidence']} kw={s['keyword']}")

    # Aggregate index: (+1*bullish -1*bearish) / total
    total = sum(scores.values())
    gsi = round((scores["bullish"] - scores["bearish"]) / max(total, 1), 3)

    report = {
        "date": today,
        "gold_sentiment_index": gsi,
        "bullish_count": scores["bullish"],
        "bearish_count": scores["bearish"],
        "neutral_count": scores["neutral"],
        "total_scored": total,
        "entries": entries,
        "scanned_kols": len(kols),
    }

    # Save
    out_file = RESULTS_DIR / f"sentiment_{today}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Update state
    state["user_cache"] = user_cache
    state["seen_tweets"] = list(seen_tweets)[-5000:]  # keep last 5000
    STATE_FILE.write_text(json.dumps(state, indent=2))

    # Also write latest symlink
    latest = RESULTS_DIR / "sentiment_latest.json"
    latest.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return report


def main():
    import argparse

    p = argparse.ArgumentParser(description="WhaleTrail Sentiment Scanner")
    p.add_argument("--account", help="Scan a single X account")
    args = p.parse_args()

    print(f"🐋 WhaleTrail Sentiment | {date.today().isoformat()}")
    print(f"   KOLs: {len(GOLD_KOLS) if not args.account else 1}")

    report = scan(args)
    gsi = report["gold_sentiment_index"]
    label = (
        "🟢 bullish" if gsi > 0.15
        else "🔴 bearish" if gsi < -0.15
        else "🟡 neutral"
    )
    print(f"\n{'='*50}")
    print(f"  Gold Sentiment Index: {gsi:.3f}  {label}")
    print(f"  Bullish: {report['bullish_count']}  "
          f"Bearish: {report['bearish_count']}  "
          f"Neutral: {report['neutral_count']}")
    print(f"  Saved: results/sentiment_{report['date']}.json")


if __name__ == "__main__":
    main()
