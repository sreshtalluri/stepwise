"""Latency of gate.py on a Modal CPU container (cpu=2, region us), ephemeral: `modal run modal_bench.py`.
Nothing is deployed and nothing is written to any Volume; clips ride along as image files."""
import os
import modal

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = ["pos/eval_solo-07.mp4", "pos/eval_solo-01.mp4",
         "neg/synth_still_music_dc32.mp4", "neg/talking_head_was_ist_ein_vlog_webm.mp4", "neg/cooking_webm.mp4"]
image = (modal.Image.debian_slim(python_version="3.12").apt_install("ffmpeg")
         .pip_install("torch==2.8.0", index_url="https://download.pytorch.org/whl/cpu")
         .pip_install("transformers", "onnxruntime", "rtmlib", "opencv-python-headless", "numpy", "pillow", "nudenet")
         .run_commands("python -c \"from transformers import CLIPModel, CLIPProcessor; "
                       "CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')\"")
         .add_local_file(os.path.join(HERE, "gate.py"), "/app/gate.py"))
for c in CLIPS:
    image = image.add_local_file(os.path.join(os.environ.get("DANCE_GATE_DATA") or os.path.join(HERE, ".data"), "clips", c), f"/clips/{os.path.basename(c)}")
app = modal.App("dance-gate-bench", image=image)


@app.function(cpu=2, memory=4096, region="us", timeout=900)
def bench():
    import sys, time
    sys.path.insert(0, "/app")
    t = time.time()
    import gate
    g = gate.Gate(threads=2)
    load = time.time() - t
    out = [g(f"/clips/{os.path.basename(c)}") for c in CLIPS]
    out2 = [g(f"/clips/{os.path.basename(c)}") for c in CLIPS]  # warm second pass
    return load, out, out2


@app.local_entrypoint()
def main():
    import json
    load, out, out2 = bench.remote()
    print("load (imports + models, warm image):", round(load, 1), "s")
    for a, b in zip(out, out2):
        print(json.dumps({"clip": a["clip"], "accept": a["accept"], "first": a["seconds"], "second": b["seconds"]}))
