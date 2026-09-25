"""Openly licensed test clips from Wikimedia Commons (every file there is CC/PD).

Writes clips/{neg,pos,amb}/<slug>.mp4 (a <=20 s, 480p cut) and manifest.json with the
source page, licence and author for each. Usage: python fetch_commons.py
"""
import json, os, re, subprocess, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
UA = {"User-Agent": "stepwise-dance-gate-research/0.1 (sreshta research; offline eval)"}

# (label, category, search, how many)
QUERIES = [
    ("neg", "talking_head", "interview filetype:video", 4),
    ("neg", "talking_head", "vlog filetype:video", 3),
    ("neg", "lecture", "lecture talk filetype:video", 2),
    ("neg", "cooking", "cooking filetype:video", 4),
    ("neg", "basketball", "basketball filetype:video", 3),
    ("neg", "running", "running race filetype:video", 3),
    ("neg", "yoga", "yoga filetype:video", 3),
    ("neg", "workout", "workout exercise filetype:video", 3),
    ("neg", "gymnastics", "gymnastics filetype:video", 2),
    ("neg", "martial_arts", "karate kata filetype:video", 2),
    ("neg", "walking", "walking street filetype:video", 3),
    ("neg", "pets", "cat playing filetype:video", 2),
    ("neg", "pets", "dog filetype:video", 2),
    ("neg", "gameplay", "gameplay filetype:video", 3),
    ("neg", "screen", "screencast tutorial filetype:video", 2),
    ("neg", "music_performer", "singing song filetype:video", 3),
    ("neg", "music_performer", "playing guitar filetype:video", 2),
    ("neg", "concert", "concert crowd filetype:video", 2),
    ("neg", "skateboard", "skateboarding filetype:video", 2),
    ("neg", "swimwear", "beach volleyball filetype:video", 2),
    ("neg", "traffic", "traffic road filetype:video", 2),
    ("neg", "nature", "waterfall filetype:video", 2),
    ("neg", "parade_march", "military parade march filetype:video", 2),
    ("pos", "folk", "folk dance filetype:video", 4),
    ("pos", "ballet", "ballet filetype:video", 3),
    ("pos", "hiphop", "hip hop dance filetype:video", 3),
    ("pos", "breakdance", "breakdance filetype:video", 3),
    ("pos", "salsa", "salsa dancing filetype:video", 2),
    ("pos", "tap", "tap dance filetype:video", 2),
    ("pos", "bollywood", "bollywood dance filetype:video", 2),
    ("pos", "kpop", "kpop dance cover filetype:video", 2),
    ("pos", "contemporary", "contemporary dance filetype:video", 2),
    ("amb", "zumba", "zumba filetype:video", 2),
    ("amb", "cheer", "cheerleading filetype:video", 2),
    # round 2: hard negatives (rhythmic or person-centred, not dance) and wider positives
    ("neg", "sign_language", "sign language filetype:video", 3),
    ("neg", "jump_rope", "jump rope skipping filetype:video", 2),
    ("neg", "boxing", "shadow boxing training filetype:video", 2),
    ("neg", "tai_chi", "tai chi filetype:video", 2),
    ("neg", "juggling", "juggling filetype:video", 2),
    ("neg", "hula_hoop", "hula hoop filetype:video", 2),
    ("neg", "conducting", "conductor orchestra filetype:video", 2),
    ("neg", "drumming", "drumming drummer filetype:video", 3),
    ("neg", "makeup", "makeup tutorial filetype:video", 2),
    ("neg", "stretching", "stretching exercises filetype:video", 2),
    ("neg", "jumping_jacks", "jumping jacks filetype:video", 2),
    ("neg", "selfie", "selfie video filetype:video", 2),
    ("pos", "flamenco", "flamenco filetype:video", 2),
    ("pos", "bharatanatyam", "bharatanatyam filetype:video", 2),
    ("pos", "irish", "irish dance filetype:video", 2),
    ("pos", "line", "line dance filetype:video", 2),
    ("pos", "street", "street dance filetype:video", 3),
    ("pos", "lesson", "dance lesson filetype:video", 2),
    ("pos", "waltz", "waltz dancing filetype:video", 2),
    ("pos", "hula", "hula dance filetype:video", 2),
    ("amb", "aerobics", "aerobics filetype:video", 2),
]


def get(url):
    for wait in (2, 15, 60):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    raise SystemExit("rate limited")


def search(q, n):
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": q,
              "gsrnamespace": 6, "gsrlimit": n * 4, "prop": "videoinfo",
              "viprop": "url|size|mediatype|derivatives|extmetadata"}
    data = json.loads(get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)))
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return pages


def pick(vi):
    ders = vi.get("derivatives") or []
    for want in ("360p.vp9.webm", "360p.webm", "480p.vp9.webm", "480p.webm"):
        for d in ders:
            if d.get("transcodekey") == want:
                return d["src"]
    return vi.get("url")


def main():
    manifest_path = os.path.join(HERE, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}
    seen = {m["page"] for m in manifest.values()}
    for label, cat, q, n in QUERIES:
        got = sum(1 for m in manifest.values() if m["query"] == q)
        if got:
            continue  # searched in an earlier run
        for p in search(q, n):
            if got >= n:
                break
            vi = (p.get("videoinfo") or [{}])[0]
            if vi.get("mediatype") != "VIDEO" or p["title"] in seen:
                continue
            meta = vi.get("extmetadata", {})
            dur = float(meta.get("Duration", {}).get("value", 0) or 0) or None
            src = pick(vi)
            slug = f"{cat}_{re.sub(r'[^a-z0-9]+', '_', p['title'][5:].lower())[:40].strip('_')}"
            out = os.path.join(DATA, "clips", label, slug + ".mp4")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            start = min(0.15 * dur, 30) if dur and dur > 30 else 0
            cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-i", src, "-t", "20",
                   "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                   "-c:a", "aac", "-b:a", "96k", "-ac", "2", out]
            part = out + ".part"
            r = subprocess.run(["curl", "-sf", "-A", UA["User-Agent"], "-r", "0-8000000", "-o", part, src])
            time.sleep(1)
            if r.returncode != 0:
                print("skip", p["title"], "curl", r.returncode, file=sys.stderr)
                continue
            cmd[cmd.index(src)] = part
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            os.unlink(part)
            if r.returncode != 0:
                print("skip", p["title"], r.stderr[-160:], file=sys.stderr)
                continue
            if not os.path.exists(out) or os.path.getsize(out) < 20000:
                continue
            manifest[slug] = {"label": label, "category": cat, "query": q, "page": p["title"],
                              "url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(p["title"].replace(" ", "_")),
                              "licence": meta.get("LicenseShortName", {}).get("value"),
                              "artist": re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", ""))[:80]}
            seen.add(p["title"])
            got += 1
            print(label, slug, manifest[slug]["licence"], flush=True)
            json.dump(manifest, open(manifest_path, "w"), indent=1)


if __name__ == "__main__":
    main()
