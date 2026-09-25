"""Options B, C, D per clip, cached as cache/<method>/<name>.json with latency.

    python extract_bcd.py <method> clips/*/*.mp4
    methods: kinetics | xclip | clip | smolvlm | falconsai | nudenet
"""
import json, os, sys, time
import numpy as np
import torch
from extract_a import decode

torch.set_num_threads(2)  # what a 2-CPU Modal container would have
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")

DANCE_K400 = {"belly dancing", "breakdancing", "capoeira", "cheerleading", "country line dancing", "dancing ballet",
              "dancing charleston", "dancing gangnam style", "dancing macarena", "jumpstyle dancing", "krumping",
              "robot dancing", "salsa dancing", "swing dancing", "tango dancing", "tap dancing", "zumba"}
POS = ["a person dancing", "people dancing", "a dance performance", "a dance tutorial video",
       "a person dancing in their room", "a dance choreography"]
NEG = ["a person talking to the camera", "a person cooking food", "people playing a sport", "a person exercising",
       "a person doing yoga", "a person walking", "a video game", "a screen recording", "an animal", "a pet",
       "a person singing", "a person playing a musical instrument", "a landscape", "traffic on a road",
       "a person standing still", "a crowd at a concert", "a lecture", "a person skateboarding", "people running"]


def at(frames, fracs, n=1):
    idx = []
    for f in fracs:
        c = int(f * (len(frames) - 1))
        idx += [min(max(c + k - n // 2, 0), len(frames) - 1) for k in range(n)]
    return [np.ascontiguousarray(frames[i][:, :, ::-1]) for i in idx]  # BGR -> RGB


def load(method):
    if method == "kinetics":
        from torchvision.models.video import mvit_v2_s, MViT_V2_S_Weights
        w = MViT_V2_S_Weights.KINETICS400_V1
        m = mvit_v2_s(weights=w).eval()
        cats = w.meta["categories"]
        dance_idx = [i for i, c in enumerate(cats) if c in DANCE_K400]
        tf = w.transforms()

        def run(frames):
            probs = []
            for c in (0.25, 0.5, 0.75):
                clip = torch.from_numpy(np.stack(at(frames, [c], 16)).copy()).permute(0, 3, 1, 2)  # T C H W
                with torch.no_grad():
                    p = m(tf(clip).unsqueeze(0)).softmax(-1)[0]
                probs.append(p)
            p = torch.stack(probs).mean(0)
            top = p.topk(3)
            return {"score": float(p[dance_idx].sum()), "top": [[cats[i], round(float(v), 3)] for v, i in zip(top.values, top.indices)]}
        return run
    if method in ("xclip", "clip"):
        from transformers import AutoProcessor, AutoModel
        name = "microsoft/xclip-base-patch32" if method == "xclip" else "openai/clip-vit-base-patch32"
        proc = AutoProcessor.from_pretrained(name)
        m = AutoModel.from_pretrained(name).eval()
        texts = POS + NEG if method == "xclip" else [f"a photo of {t}" for t in POS + NEG]

        def run(frames):
            imgs = at(frames, np.linspace(0.1, 0.9, 8))
            with torch.no_grad():
                if method == "xclip":
                    inp = proc(text=texts, videos=[list(imgs)], return_tensors="pt", padding=True)
                    logits = m(**inp).logits_per_video[0]
                    p = logits.softmax(-1)
                else:
                    inp = proc(text=texts, images=list(imgs), return_tensors="pt", padding=True)
                    p = m(**inp).logits_per_image.softmax(-1).mean(0)
            best = int(p.argmax())
            return {"score": float(p[:len(POS)].sum()), "top": texts[best]}
        return run
    if method == "smolvlm":
        from transformers import AutoProcessor, AutoModelForImageTextToText
        from PIL import Image
        name = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
        proc = AutoProcessor.from_pretrained(name)
        m = AutoModelForImageTextToText.from_pretrained(name, torch_dtype=torch.float32).eval()
        q = ("These are frames from one short video, in order. Is a person dancing in this video? "
             "Answer with one word: yes or no.")
        yes_ids = [proc.tokenizer.encode(t, add_special_tokens=False)[0] for t in ("yes", "Yes", " yes", " Yes")]
        no_ids = [proc.tokenizer.encode(t, add_special_tokens=False)[0] for t in ("no", "No", " no", " No")]

        def run(frames):
            imgs = [Image.fromarray(np.ascontiguousarray(f)) for f in at(frames, np.linspace(0.1, 0.9, 4))]
            content = [{"type": "image"} for _ in imgs] + [{"type": "text", "text": q}]
            prompt = proc.apply_chat_template([{"role": "user", "content": content}], add_generation_prompt=True)
            inp = proc(text=prompt, images=imgs, return_tensors="pt", do_image_splitting=False)
            with torch.no_grad():
                logits = m(**inp).logits[0, -1]
            lp = logits.log_softmax(-1)
            y = torch.logsumexp(lp[yes_ids], 0); n = torch.logsumexp(lp[no_ids], 0)
            return {"score": float(torch.sigmoid(y - n))}
        return run
    if method == "falconsai":
        from transformers import pipeline
        from PIL import Image
        clf = pipeline("image-classification", model="Falconsai/nsfw_image_detection", device="cpu")

        def run(frames):
            imgs = [Image.fromarray(np.ascontiguousarray(f)) for f in at(frames, np.linspace(0.05, 0.95, 8))]
            s = [next(r["score"] for r in out if r["label"] == "nsfw") for out in clf(imgs)]
            return {"score": float(max(s)), "scores": [round(x, 3) for x in s]}
        return run
    if method == "nudenet":
        from nudenet import NudeDetector
        det = NudeDetector()
        EXPOSED = {"FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED",
                   "ANUS_EXPOSED", "BUTTOCKS_EXPOSED"}

        def run(frames):
            best, hits = 0.0, []
            for f in at(frames, np.linspace(0.05, 0.95, 8)):
                for d in det.detect(np.ascontiguousarray(f[:, :, ::-1])):  # NudeNet wants BGR
                    if d["class"] in EXPOSED:
                        best = max(best, d["score"]); hits.append([d["class"], round(d["score"], 2)])
            return {"score": best, "hits": hits}
        return run
    raise SystemExit(f"unknown method {method}")


def main(method, paths):
    out = os.path.join(DATA, "cache", method)
    os.makedirs(out, exist_ok=True)
    t = time.time(); run = load(method); load_s = time.time() - t
    print(f"{method}: load {load_s:.1f}s", flush=True)
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        dest = os.path.join(out, name + ".json")
        if os.path.exists(dest) and not os.environ.get("FORCE"):
            continue
        try:
            frames, _, _ = decode(path)
        except Exception as e:  # noqa: BLE001
            print("decode failed", name, e)
            continue
        if len(frames) < 4:
            continue
        t = time.time(); r = run(frames); r["seconds"] = time.time() - t
        json.dump(r, open(dest, "w"))
        print(method, name, {k: v for k, v in r.items() if k != "scores"}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
