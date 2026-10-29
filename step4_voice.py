"""STEP 4 — Voiceover with TTS FAILOVER (multiple ElevenLabs keys + free Edge).

Tries a pool of TTS backends in order (per TTS_ORDER): every ElevenLabs key,
then Edge TTS as the always-free final fallback so voicing never hard-fails.
When an ElevenLabs key hits its quota/unusual-activity block, it's marked dead
for the run and the next backend takes over. Reads 'images_ready' -> 'voiced'.

Keys (comma-separated) in .env:  ELEVENLABS_API_KEYS=...
pip install elevenlabs edge-tts
"""
import asyncio

import config
from store import get_by_status, update_post


def _is_quota(msg):
    m = msg.lower()
    return any(x in m for x in ("quota", "401", "unusual_activity", "rate", "429", "exceeds"))


# ---------- ElevenLabs backend ----------
class _ElevenBackend:
    kind = "elevenlabs"

    def __init__(self, key):
        self.key, self.client, self.voice_id, self.dead = key, None, None, False

    def _init(self):
        from elevenlabs.client import ElevenLabs
        self.client = ElevenLabs(api_key=self.key)
        voices = self.client.voices.get_all().voices
        chosen = None
        for v in voices:
            if v.name.lower() == config.ELEVENLABS_VOICE.lower():
                chosen = v
                break
        if chosen is None:
            for v in voices:
                if config.ELEVENLABS_VOICE.lower() in v.name.lower():
                    chosen = v
                    break
        if chosen is None and voices:
            chosen = voices[0]
        if chosen is None:
            raise RuntimeError("no voices on account")
        self.voice_id = chosen.voice_id

    def synth(self, text, out_path):
        if self.client is None:
            self._init()
        audio = self.client.text_to_speech.convert(
            voice_id=self.voice_id, model_id=config.ELEVENLABS_MODEL,
            text=text, output_format="mp3_44100_128")
        with open(out_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)


# ---------- Edge TTS backend (free) ----------
class _EdgeBackend:
    kind = "edge"
    dead = False

    def synth(self, text, out_path):
        import edge_tts

        async def go():
            c = edge_tts.Communicate(text, config.EDGE_VOICE, rate=config.EDGE_RATE)
            await c.save(str(out_path))

        asyncio.run(go())


def _build_backends():
    backends = []
    for fam in config.TTS_ORDER:
        if fam == "elevenlabs":
            backends += [_ElevenBackend(k) for k in config.ELEVENLABS_API_KEYS]
        elif fam == "edge":
            backends.append(_EdgeBackend())
    if not any(isinstance(b, _EdgeBackend) for b in backends):
        backends.append(_EdgeBackend())   # always keep a free fallback
    return backends


def _synth_one(backends, text, out_path):
    last = None
    for b in backends:
        if getattr(b, "dead", False):
            continue
        try:
            b.synth(text, out_path)
            if out_path.exists() and out_path.stat().st_size > 0:
                return b
            raise RuntimeError("empty audio")
        except Exception as e:
            last = e
            if b.kind == "elevenlabs" and _is_quota(str(e)):
                print(f"   ... elevenlabs key exhausted - switching backend")
                b.dead = True
            else:
                print(f"   ! {b.kind} error, trying next: {str(e)[:80]}")
    raise last or RuntimeError("no TTS backends available")


def run():
    backends = _build_backends()
    print(f"[voice] {len(backends)} TTS backend(s): "
          + ", ".join(b.kind for b in backends))
    todo = get_by_status("images_ready")
    print(f"[voice] {len(todo)} scripts to voice.")
    for code, post in todo.items():
        script = post.get("content", {}).get("script")
        if not script:
            continue
        out = config.AUDIO_DIR / f"{code}.mp3"
        try:
            used = _synth_one(backends, script, out)
        except Exception as e:
            print(f"   ! tts failed ({code}): {str(e)[:100]}")
            continue
        update_post(code, audio_file=str(out), status="voiced")
        print(f"   + {code} [{used.kind}]: {out.name}")
    return get_by_status("voiced")


if __name__ == "__main__":
    run()