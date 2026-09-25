"""Teacher-style cue text for proposed steps, grounded in measured features. Research prototype.

    python cue_prompt.py [lesson] [chunk#]   # writes out/cue_request.json (what we would send)
    python cue_prompt.py --check             # grounding-validator self-check

Only calls the API when ANTHROPIC_API_KEY is already set AND the `anthropic` package is installed.
Every returned cue is run through `ungrounded()`: a cue that names a body part, side, direction, turn
or level change that the step's features do not contain is dropped, not shown.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-sonnet-5"  # cheap enough per lesson; see docs/research/step-by-step-learning.md for costs

SYSTEM = """You write short practice cues for a dance-learning site, like a teacher calling out steps.
You only see MEASURED features of each step, never the video. Rules:
- Use only what the features state: body parts, the dancer's own left/right, direction, travel, turn, level, quality.
- Left/right are always the DANCER's. Never say "your left" unless the feature says so; say "their" or the part name.
- Do not name a dance move ("a shoulder pop", "a two-step") unless it follows directly from the features. Prefer plain verbs.
- If a step lists uncertain_parts, do not describe those parts in detail.
- If the features are too thin for a useful cue, return an empty cue. An empty cue is better than a guess.
- Max 8 words per cue. Counts are given; you may prefix the cue with them ("5-6:")."""

SCHEMA = {
    "type": "object",
    "properties": {"cues": {"type": "array", "items": {
        "type": "object",
        "properties": {"step": {"type": "integer"}, "cue": {"type": "string"},
                       "grounded_in": {"type": "array", "items": {"type": "string"}}},
        "required": ["step", "cue", "grounded_in"], "additionalProperties": False}}},
    "required": ["cues"], "additionalProperties": False,
}

KEEP = ("counts", "lead", "moves", "whole_body", "quality", "uncertain_parts")


def features(lesson, chunk_no):
    data = json.load(open(os.path.join(HERE, "out", "steps.json")))[lesson]
    chunk = data["chunks"][chunk_no - 1]
    return [{"step": i + 1, **{k: data["steps"][i][k] for k in KEEP}} for i in chunk["steps"]]


WORDS = {  # word in a cue -> what must appear somewhere in that step's feature text
    r"\bleft\b": "left", r"\bright\b": "right", r"\barms?\b|\bhands?\b": "arm", r"\blegs?\b|\bfoot\b|\bfeet\b|\bknee": "leg",
    r"\bhead\b": "head", r"\bturn|\bspin|\bpivot": "turn", r"\bdrop|\blow|\bsquat|\bbend": "drop",
    r"\bjump|\bhop|\brise": "jump/rise", r"\btravel|\bstep (?:forward|back)|\bwalk": "travel",
    r"\bup\b": "up", r"\bdown\b": "down", r"\bforward\b": "forward", r"\bback\b": "back",
    r"\bsharp|\bhit|\bpop|\bsnap": "sharp", r"\bsmooth|\bglide|\bflow": "smooth", r"\bhold|\bfreeze|\bpause": "hold",
}


def ungrounded(cue, feat):
    """Words in the cue with no support in the step's features (empty list = grounded)."""
    text = json.dumps(feat).lower()
    return [w for pat, need in WORDS.items() for w in re.findall(pat, cue.lower()) if need not in text]


def check():
    f = {"counts": "1–2", "lead": ["left arm"], "moves": ["left arm up"], "whole_body": [], "quality": "sharp (hits and stops)"}
    assert ungrounded("1-2: left arm hits up", f) == []
    assert ungrounded("1-2: right arm up", f) == ["right"]
    assert ungrounded("1-2: spin and drop", f) == ["spin", "drop"]
    print("ok")


def main():
    if "--check" in sys.argv:
        return check()
    lesson = sys.argv[1] if len(sys.argv) > 1 else "choreo"
    chunk_no = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    feats = features(lesson, chunk_no)
    request = dict(model=MODEL, max_tokens=2000, system=SYSTEM,
                   output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                   messages=[{"role": "user", "content": json.dumps({"steps": feats}, ensure_ascii=False)}])
    json.dump(request, open(os.path.join(HERE, "out", "cue_request.json"), "w"), indent=1, ensure_ascii=False)
    print(f"wrote out/cue_request.json ({lesson}, chunk {chunk_no}, {len(feats)} steps)")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set: not calling the API.")
        return
    import anthropic  # only needed for a live call
    resp = anthropic.Anthropic().messages.create(**request)
    if resp.stop_reason == "refusal":
        print("refused:", resp.stop_details)
        return
    cues = json.loads(next(b.text for b in resp.content if b.type == "text"))["cues"]
    by_step = {f["step"]: f for f in feats}
    for c in cues:
        bad = ungrounded(c["cue"], by_step.get(c["step"], {}))
        print(f"{c['step']:>3} {'DROP ' + str(bad) if bad else 'ok  '} {c['cue']}")
    print("usage:", resp.usage)


if __name__ == "__main__":
    main()
