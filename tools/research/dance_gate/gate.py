"""The recommended dance gate, end to end on local files, with per-stage timings.

    python gate.py [--pose] clip.mp4 [...]      # one JSON line per clip

Reject when EITHER:
  * CLIP zero-shot "dance" probability < CLIP_MIN, averaged over 8 frames spread across the clip, or
  * the picture never changes: median mean-abs difference between consecutive 2 fps grey frames
    (160x90) over the first 16 s < STILL_MAX (a photo or a frozen frame over music).
With --pose, also reject when RTMO-s finds no person (score > 0.5) in >= 70% of those 32 frames, or the
person's limbs never move (median body-relative limb speed < 0.02 body heights/s). Measured: +8 points of
negatives rejected, but ~5 s more per clip on a 2-CPU Modal container.
Everything else passes: a borderline dance gets through; the cost of that is one GPU run.

Also reports NudeNet's max "exposed" score over the CLIP frames (shadow only; never rejects here).
Research prototype: torch CLIP for convenience; production would run the same image tower as ONNX
with the prompt embeddings precomputed.
"""
import json, subprocess, sys, time
import numpy as np

CLIP_MIN, STILL_MAX = 0.4, 0.1
PERSON_MIN, LIMB_MIN = 0.3, 0.02
FPS, SECONDS, CLIP_FRAMES, LONG_SIDE = 2, 16, 8, 480
RTMO_S = ("https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/"
          "rtmo-s_8xb32-600e_body7-640x640-dac2bf74_20231211.zip")
POS = ["a person dancing", "people dancing", "a dance performance", "a dance tutorial video",
       "a person dancing in their room", "a dance choreography"]
NEG = ["a person talking to the camera", "a person cooking food", "people playing a sport", "a person exercising",
       "a person doing yoga", "a person walking", "a video game", "a screen recording", "an animal", "a pet",
       "a person singing", "a person playing a musical instrument", "a landscape", "traffic on a road",
       "a person standing still", "a crowd at a concert", "a lecture", "a person skateboarding", "people running"]
LIMBS = [9, 10, 15, 16, 13, 14, 7, 8]  # wrists, ankles, knees, elbows (COCO-17)
EXPOSED = {"FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED", "ANUS_EXPOSED",
           "BUTTOCKS_EXPOSED"}


def sample(path):
    """Frames at FPS over the clip (<= 60 s), long side LONG_SIDE, BGR, in memory. Nothing touches disk."""
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height:stream_side_data=rotation", "-of", "json", path],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    w, h = s["width"], s["height"]
    if abs(int(next((d.get("rotation", 0) for d in s.get("side_data_list", []) if "rotation" in d), 0))) in (90, 270):
        w, h = h, w
    W, H = ((LONG_SIDE, int(round(h * LONG_SIDE / w / 2)) * 2) if w >= h
            else (int(round(w * LONG_SIDE / h / 2)) * 2, LONG_SIDE))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", "60", "-i", path, "-an", "-vf", f"fps={FPS},scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)


def stillness(frames):
    import cv2
    g = np.stack([cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA)
                  for f in frames]).astype(np.float32)
    return float(np.median(np.abs(np.diff(g, axis=0)).mean(axis=(1, 2)))) if len(g) > 2 else 0.0


def decide(dance, still, person=None, limb=None):
    """[] = accept; otherwise the reasons to reject. person/limb are None without --pose."""
    reasons = []
    if dance < CLIP_MIN:
        reasons.append("looks_like_something_else")
    if still < STILL_MAX:
        reasons.append("nothing_moves")
    if person is not None and person < PERSON_MIN:
        reasons.append("no_person")
    if person is not None and person >= PERSON_MIN and limb < LIMB_MIN:
        reasons.append("nobody_moves")
    return reasons


class Gate:
    def __init__(self, pose=False, threads=2):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        torch.set_num_threads(threads)
        self.proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
        with torch.no_grad():  # the prompts never change: embed them once per container
            t = self.proc(text=[f"a photo of {p}" for p in POS + NEG], return_tensors="pt", padding=True)
            e = self.clip.text_projection(self.clip.text_model(**t).pooler_output)
            self.text = e / e.norm(dim=-1, keepdim=True)
        self.rtmo = None
        if pose:
            import onnxruntime as ort
            from rtmlib import RTMO
            ort.set_default_logger_severity(3)
            self.rtmo = RTMO(onnx_model=RTMO_S, model_input_size=(640, 640), backend="onnxruntime", device="cpu")
            so = ort.SessionOptions(); so.intra_op_num_threads = threads
            self.rtmo.session = ort.InferenceSession(self.rtmo.session._model_path, so,
                                                     providers=["CPUExecutionProvider"])
        self.nude = None
        try:
            from nudenet import NudeDetector
            self.nude = NudeDetector()
        except ImportError:
            pass

    def person_motion(self, frames):
        kp, box = [], []
        for f in frames:
            padded, ratio = self.rtmo.preprocess(f)
            det, pose = self.rtmo.inference(padded)
            j = int(det[0, :, 4].argmax())
            ok = det[0, j, 4] > 0.5
            box.append(det[0, j, :4] / ratio if ok else None)
            kp.append(pose[0, j] / [ratio, ratio, 1] if ok else None)
        speeds = []
        for i in range(1, len(kp)):
            if kp[i] is None or kp[i - 1] is None:
                continue
            rel = [(k[:, :2] - k[[11, 12], :2].mean(0)) / max(b[3] - b[1], 1.0)
                   for k, b in ((kp[i - 1], box[i - 1]), (kp[i], box[i]))]
            ok = ((kp[i][:, 2] > 0.3) & (kp[i - 1][:, 2] > 0.3))[LIMBS]
            v = np.clip(np.linalg.norm(rel[1] - rel[0], axis=1) * FPS, 0, 8)[LIMBS][ok]
            if len(v):
                speeds.append(v.mean())
        present = float(np.mean([b is not None for b in box])) if box else 0.0
        return present, float(np.median(speeds)) if speeds else 0.0

    def clip_score(self, frames):
        import torch
        with torch.no_grad():
            px = self.proc(images=[np.ascontiguousarray(f[:, :, ::-1]) for f in frames],
                           return_tensors="pt")["pixel_values"]
            e = self.clip.visual_projection(self.clip.vision_model(pixel_values=px).pooler_output)
            e = e / e.norm(dim=-1, keepdim=True)
            p = (self.clip.logit_scale.exp() * e @ self.text.T).softmax(-1).mean(0)
        return float(p[:len(POS)].sum())

    def nsfw(self, frames):
        if self.nude is None:
            return None
        return max([d["score"] for f in frames for d in self.nude.detect(np.ascontiguousarray(f))
                    if d["class"] in EXPOSED] or [0.0])

    def __call__(self, path):
        t = {}
        t0 = time.time(); frames = sample(path); t["decode"] = time.time() - t0
        head = frames[: FPS * SECONDS]
        t0 = time.time(); still = stillness(head); t["still"] = time.time() - t0
        picked = [frames[int(round(i))] for i in np.linspace(0.1, 0.9, CLIP_FRAMES) * (len(frames) - 1)]
        t0 = time.time(); dance = self.clip_score(picked); t["clip"] = time.time() - t0
        person = limb = None
        if self.rtmo is not None:
            t0 = time.time(); person, limb = self.person_motion(head); t["pose"] = time.time() - t0
        t0 = time.time(); nsfw = self.nsfw(picked); t["nsfw"] = time.time() - t0
        reasons = decide(dance, still, person, limb)
        scores = {"dance": round(dance, 3), "still": round(still, 2),
                  "nsfw": None if nsfw is None else round(nsfw, 3)}
        if person is not None:
            scores.update(person=round(person, 2), limb=round(limb, 3))
        return {"clip": path.rsplit("/", 1)[-1], "accept": not reasons, "reasons": reasons, "scores": scores,
                "seconds": {k: round(v, 2) for k, v in t.items()} | {"total": round(sum(t.values()), 2)}}


def _selfcheck():
    assert decide(0.99, 12.0) == []                                   # a dance
    assert decide(0.45, 0.46) == []                                   # far-away group dance, low scores: passes
    assert decide(0.99, 0.0) == ["nothing_moves"]                     # a dancer's photo over music
    assert decide(0.2, 8.0) == ["looks_like_something_else"]          # a vlog
    assert decide(0.99, 5.0, person=0.1, limb=0.0) == ["no_person"]
    assert decide(0.99, 5.0, person=1.0, limb=0.0) == ["nobody_moves"]


if __name__ == "__main__":
    _selfcheck()
    args = sys.argv[1:]
    gate = Gate(pose="--pose" in args)
    for p in (a for a in args if a != "--pose"):
        print(json.dumps(gate(p)), flush=True)
