"""STEP 2 — Rewrite posts into ORIGINAL commentary, with LLM FAILOVER.

Tries a pool of backends in order (every Groq key, then every Gemini key, per
LLM_ORDER). When one returns a quota/rate error, it's marked dead for the run and
the next backend takes over. Reads 'new' posts -> status 'rewritten'.

Keys (comma-separated) in .env:  GROQ_API_KEYS=...   GEMINI_API_KEYS=...
pip install groq google-genai
"""
import json
import re

import config
from store import get_by_status, update_post

PROMPT = """You are a football content writer creating an ORIGINAL short-form
commentary video script. The news can be ANY type of football story: a transfer,
a big match result, a World Cup moment, a goal record, a trophy win, or any major
player news. Write entirely in your OWN words — never copy source phrasing.
Match the energy to the story: explosive for goals/wins, dramatic for transfers.

News item:
\"\"\"{caption}\"\"\"

Return ONLY valid JSON (no markdown, no backticks) with these keys:
{{
  "type": "one of: transfer | match | goal | worldcup | tournament | player | other",
  "script": "spoken narration, 30-45 seconds, ~80-110 words, energetic, ends with a call to follow",
  "title": "YouTube Shorts title, <80 chars, punchy",
  "description": "2-3 sentence video description",
  "tags": ["8-12 lowercase keyword tags"],
  "subjects": ["the specific REAL people and clubs in this news — most important first, e.g. 'Kylian Mbappe', 'Real Madrid', 'World Cup 2026'"],
  "image_query": "3-5 word fallback search phrase for relevant stock football images",
  "importance": 8
}}
importance score (integer 1-10):
  10 = World Cup/CL final, confirmed blockbuster "here we go" signing
  8-9 = World Cup goal/win, major trophy, big confirmed transfer, hat-trick by a superstar
  6-7 = Important league result, big player goal/record, serious transfer bid, injury to key player
  4-5 = Regular match result, mid-table club signing, minor loan, rumour without substance
  1-3 = Opinion piece, preview, irrelevant minor news
If the item is not about football at all, return {{"skip": true}}.
"""

_BAD = ("whisper", "tts", "guard", "embed", "allam", "moderation")


def _is_quota(msg):
    m = msg.lower()
    return any(x in m for x in ("429", "resource_exhausted", "quota", "rate limit", "too many"))


def _pick_groq(client):
    try:
        ids = [m.id for m in client.models.list().data]
    except Exception:
        return config.GROQ_MODEL
    chat = [i for i in ids if not any(b in i.lower() for b in _BAD)]
    if config.GROQ_MODEL in chat:
        return config.GROQ_MODEL
    chat.sort(key=lambda n: ("versatile" in n) * 4 + ("70b" in n) * 3 + ("instant" in n), reverse=True)
    return chat[0] if chat else config.GROQ_MODEL


def _pick_gemini(client):
    try:
        avail = [m.name.replace("models/", "") for m in client.models.list()
                 if "generateContent" in (getattr(m, "supported_actions", None) or [])]
    except Exception:
        return config.GEMINI_MODEL
    if config.GEMINI_MODEL in avail:
        return config.GEMINI_MODEL
    avail.sort(key=lambda n: ("flash" in n) * 3 + ("lite" in n) - ("preview" in n) * 2, reverse=True)
    return avail[0] if avail else config.GEMINI_MODEL


class _Backend:
    def __init__(self, kind, key):
        self.kind, self.key, self.client, self.model, self.dead = kind, key, None, None, False

    def _init(self):
        if self.kind == "groq":
            from groq import Groq
            self.client = Groq(api_key=self.key)
            self.model = _pick_groq(self.client)
        else:
            from google import genai
            self.client = genai.Client(api_key=self.key)
            self.model = _pick_gemini(self.client)

    def generate(self, prompt):
        if self.client is None:
            self._init()
        if self.kind == "groq":
            r = self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}],
                temperature=0.9)
            return r.choices[0].message.content
        r = self.client.models.generate_content(model=self.model, contents=prompt)
        return r.text


def _build_backends():
    pools = {"groq": config.GROQ_API_KEYS, "gemini": config.GEMINI_API_KEYS}
    backends = []
    for fam in config.LLM_ORDER:
        for key in pools.get(fam, []):
            backends.append(_Backend(fam, key))
    return backends


def _generate(backends, prompt):
    last = None
    for b in backends:
        if b.dead:
            continue
        try:
            return b.generate(prompt), b
        except Exception as e:
            last = e
            if _is_quota(str(e)):
                print(f"   ... {b.kind} key exhausted - switching backend")
                b.dead = True
            else:
                print(f"   ! {b.kind} error, trying next: {str(e)[:80]}")
    raise last or RuntimeError("no LLM backends available")


def _parse_json(text):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


def run():
    backends = _build_backends()
    if not backends:
        raise SystemExit("Set GROQ_API_KEYS and/or GEMINI_API_KEYS in .env")
    print(f"[rewrite] {len(backends)} LLM backend(s): "
          + ", ".join(f"{b.kind}#{i+1}" for i, b in enumerate(backends)))
    todo = get_by_status("new")
    print(f"[rewrite] {len(todo)} posts to rewrite.")
    for code, post in todo.items():
        caption = (post.get("caption") or "").strip()
        if not caption:
            update_post(code, status="skipped", skip_reason="empty caption")
            continue
        try:
            text, used = _generate(backends, PROMPT.format(caption=caption))
            content = _parse_json(text)
        except Exception as e:
            print(f"   ! all backends failed ({code}): {str(e)[:100]}")
            continue
        if content.get("skip"):
            update_post(code, status="skipped", skip_reason="not football news")
            print(f"   - {code}: skipped (not news)")
            continue
        score = int(content.get("importance") or 10)
        if score < config.MIN_IMPORTANCE:
            update_post(code, status="skipped",
                        skip_reason=f"importance {score}/10 below threshold {config.MIN_IMPORTANCE}")
            print(f"   - {code}: skipped (importance {score}/10)")
            continue
        update_post(code, content=content, status="rewritten")
        print(f"   + {code} [{used.kind}] importance={score}/10: {content.get('title', '')[:50]}")
    return get_by_status("rewritten")


if __name__ == "__main__":
    run()