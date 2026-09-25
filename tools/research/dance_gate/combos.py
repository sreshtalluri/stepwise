"""Candidate gate rules over results.json. A rule returns True = REJECT."""
import json, os
d = json.load(open(os.path.join(DATA, "results.json")))["clips"]
OURS = ("job_", "eval_", "synth_muted")


def a(v, k, default=0.0):
    return (v.get("a_feats") or {}).get(k, default)


def al(v, k, default=0.0):
    return (v.get("a_lite_feats") or {}).get(k, default)


def still_or_empty(v):
    """A-lite: nobody in >= 70% of 32 sampled frames, or the person never moves."""
    return al(v, "person_frac") < 0.3 or al(v, "limb") < 0.02


RULES = {
    "A-lite (2 fps, 16 s): no person OR frozen": still_or_empty,
    "RECOMMENDED: CLIP < 0.5 OR A-lite(no person OR frozen)": lambda v: v["clip"] < 0.5 or still_or_empty(v),
    "CLIP < 0.4 OR A-lite(no person OR frozen)": lambda v: v["clip"] < 0.4 or still_or_empty(v),
    "CLIP < 0.50": lambda v: v["clip"] < 0.50,
    "CLIP < 0.40": lambda v: v["clip"] < 0.40,
    "SmolVLM < 0.15": lambda v: v["smolvlm"] < 0.15,
    "X-CLIP < 0.20": lambda v: v["xclip"] < 0.20,
    "Kinetics < 0.005": lambda v: v["kinetics"] < 0.005,
    "A: no person (<30% frames)": lambda v: a(v, "person_frac") < 0.3,
    "A: no person OR no full body (<15%)": lambda v: a(v, "person_frac") < 0.3 or a(v, "full_body") < 0.15,
    "A: ... OR frozen (limb < 0.02)": lambda v: a(v, "person_frac") < 0.3 or a(v, "full_body") < 0.15 or a(v, "limb") < 0.02,
    "CLIP < 0.5 OR A(person/full body/frozen)": lambda v: v["clip"] < 0.5 or a(v, "person_frac") < 0.3
        or a(v, "full_body") < 0.15 or a(v, "limb") < 0.02,
    "CLIP < 0.4 OR A(person/full body/frozen)": lambda v: v["clip"] < 0.4 or a(v, "person_frac") < 0.3
        or a(v, "full_body") < 0.15 or a(v, "limb") < 0.02,
    "SmolVLM < 0.15 OR A(...)": lambda v: v["smolvlm"] < 0.15 or a(v, "person_frac") < 0.3
        or a(v, "full_body") < 0.15 or a(v, "limb") < 0.02,
}

rows = []
for name, rule in RULES.items():
    pos = [k for k, v in d.items() if v["label"] == "pos"]
    neg = [k for k, v in d.items() if v["label"] == "neg"]
    amb = [k for k, v in d.items() if v["label"] == "amb"]
    fr = [k for k in pos if rule(d[k])]
    tn = [k for k in neg if rule(d[k])]
    passed_neg = [k for k in neg if not rule(d[k])]
    ours = [k for k in pos if k.startswith(OURS)]
    fr_ours = [k for k in ours if rule(d[k])]
    tp = len(pos) - len(fr)
    prec = tp / (tp + len(passed_neg))
    print(f"\n## {name}\n recall {tp}/{len(pos)} = {tp/len(pos):.2f}; false rejects {len(fr)} (ours {len(fr_ours)}/{len(ours)}) {fr}\n"
          f" negatives rejected {len(tn)}/{len(neg)} = {len(tn)/len(neg):.2f}; precision of 'dance' {prec:.2f}\n"
          f" ambiguous rejected {sum(rule(d[k]) for k in amb)}/{len(amb)}\n negatives let through: {sorted(passed_neg)}")
    rows.append({"rule": name, "recall": tp / len(pos), "false_rejects": len(fr), "false_rejects_ours": len(fr_ours),
                 "n_ours": len(ours), "neg_rejected": len(tn) / len(neg), "precision": prec, "n_pos": len(pos), "n_neg": len(neg)})
json.dump(rows, open(os.path.join(DATA, "combos.json"), "w"), indent=1)
