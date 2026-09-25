"""Precision/recall of gate.py output against the folder labels, at several CLIP_MIN.

    python score_gate.py gate_results.jsonl
"""
import glob, json, os, sys
import numpy as np
import gate

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
lab = {os.path.basename(p): p.split(os.sep)[-2] for p in glob.glob(os.path.join(DATA, "clips", "*", "*.mp4"))}
R = [json.loads(l) for l in open(sys.argv[1])]
R = [r for r in R if lab.get(r["clip"]) in ("pos", "neg", "amb")]
OURS = ("job_", "eval_", "synth_muted")
for thr in (0.3, 0.4, 0.5):
    gate.CLIP_MIN = thr
    rej = lambda r: bool(gate.decide(r["scores"]["dance"], r["scores"]["still"], r["scores"].get("person"),
                                     r["scores"].get("limb")))
    pos = [r for r in R if lab[r["clip"]] == "pos"]; neg = [r for r in R if lab[r["clip"]] == "neg"]
    amb = [r for r in R if lab[r["clip"]] == "amb"]
    fr = [r["clip"] for r in pos if rej(r)]
    tn = sum(rej(r) for r in neg); tp = len(pos) - len(fr); fp = len(neg) - tn
    print(f"CLIP_MIN={thr}: recall {tp}/{len(pos)}, false rejects {fr}; negatives rejected {tn}/{len(neg)} "
          f"({tn/len(neg):.0%}); precision {tp/(tp+fp):.2f}; ambiguous rejected {sum(rej(r) for r in amb)}/{len(amb)}")
    if thr == 0.4:
        print("  negatives let through:", sorted(r["clip"][:40] for r in neg if not rej(r)))
print("lowest dance scores among positives:",
      sorted((r["scores"]["dance"], r["clip"][:30]) for r in R if lab[r["clip"]] == "pos")[:4])
ours = [r for r in R if r["clip"].startswith(OURS)]
print("our lessons: min dance", min(r["scores"]["dance"] for r in ours), "min still", min(r["scores"]["still"] for r in ours))
for k in R[0]["seconds"]:
    v = [r["seconds"][k] for r in R]
    print(f"{k}: median {np.median(v):.2f}s p90 {np.percentile(v, 90):.2f}s")
print("nsfw >= 0.5:", [(r["clip"][:30], lab[r["clip"]], r["scores"]["nsfw"]) for r in R if (r["scores"]["nsfw"] or 0) >= 0.5])
