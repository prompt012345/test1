import os
import re

import requests
from flask import Flask, request

PAGE_ACCESS_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
TRIGGER = os.environ.get("TRIGGER", "67")
REPLY = os.environ.get("REPLY", "89")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v21.0")

app = Flask(__name__)

trigger_pattern = re.compile(rf"(?<!\w){re.escape(TRIGGER)}(?!\w)")
seen_comments = set()


def is_own_comment(actor_id: str, page_id: str) -> bool:
    return bool(actor_id) and actor_id == page_id


def reply_to_comment(comment_id: str) -> None:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{comment_id}/comments"
    requests.post(
        url,
        json={"message": REPLY, "access_token": PAGE_ACCESS_TOKEN},
        timeout=10,
    ).raise_for_status()


def get_page_id() -> str:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/me"
    response = requests.get(
        url,
        params={"fields": "id", "access_token": PAGE_ACCESS_TOKEN},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["id"]


page_id_cache = None


def handle_comment(change: dict) -> None:
    global page_id_cache

    value = change.get("value", {})
    comment_id = value.get("comment_id") or value.get("post_id")
    if not comment_id or comment_id in seen_comments:
        return

    message = (value.get("message") or "").strip()
    if not trigger_pattern.search(message):
        return

    if page_id_cache is None:
        page_id_cache = get_page_id()
    if is_own_comment(value.get("from", {}).get("id", ""), page_id_cache):
        return

    seen_comments.add(comment_id)
    reply_to_comment(comment_id)


@app.get("/webhook")
def verify():
    if request.args.get("hub.verify_token") != VERIFY_TOKEN:
        return "Forbidden", 403
    return request.args.get("hub.challenge", "")


@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    if payload.get("object") != "page":
        return "EVENT_RECEIVED", 200

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "feed":
                try:
                    handle_comment(change)
                except requests.RequestException:
                    return "ERROR", 500
    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
