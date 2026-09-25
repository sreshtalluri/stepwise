"""Option A raw signals, cached per clip: RTMO-s keypoints at 8 fps over the whole clip
(so cheaper sampling can be simulated offline), audio pulse features, Beat This! beats.

    python extract_a.py clips/*/*.mp4   -> cache/a/<name>.npz
"""
import json, os, subprocess, sys, time
import numpy as np
import onnxruntime as ort
from rtmlib import RTMO

ort.set_default_logger_severity(3)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
OUT = os.path.join(DATA, "cache", "a")
FPS = 8
LONG = 480
RTMO_S = ("https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/"
          "rtmo-s_8xb32-600e_body7-640x640-dac2bf74_20231211.zip")


def decode(path, fps=FPS, long=LONG):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height:stream_side_data=rotation", "-of", "json", path],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    w, h = s["width"], s["height"]
    rot = abs(int(next((d.get("rotation", 0) for d in s.get("side_data_list", []) if "rotation" in d), 0)))
    if rot in (90, 270):
        w, h = h, w
    if w >= h:
        W, H = long, int(round(h * long / w / 2)) * 2
    else:
        W, H = int(round(w * long / h / 2)) * 2, long
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps},scale={W}:{H}", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
    return frames, W, H


def audio(path, sr=22050):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32), sr


def main(paths):
    os.makedirs(OUT, exist_ok=True)
    model = RTMO(onnx_model=RTMO_S, model_input_size=(640, 640), backend="onnxruntime", device="cpu")
    so = ort.SessionOptions(); so.intra_op_num_threads = 2
    model.session = ort.InferenceSession(model.session._model_path, so, providers=["CPUExecutionProvider"])
    from beat_this.inference import File2Beats
    f2b = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
    import librosa
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        dest = os.path.join(OUT, name + ".npz")
        if os.path.exists(dest):
            continue
        t0 = time.time()
        try:
            frames, W, H = decode(path)
        except Exception as e:  # noqa: BLE001
            print("decode failed", name, e)
            continue
        t_dec = time.time() - t0
        K = np.zeros((len(frames), 6, 17, 3), np.float32)  # up to 6 people: x/W, y/H, score
        B = np.zeros((len(frames), 6, 5), np.float32)       # box x0 y0 x1 y1 (norm), score
        t1 = time.time()
        for i, f in enumerate(frames):
            padded, ratio = model.preprocess(f)
            det, pose = model.inference(padded)
            sc = det[0, :, 4]
            keep = np.argsort(-sc)[:6]
            keep = keep[sc[keep] > 0.1]
            for j, k in enumerate(keep):
                bx = det[0, k, :4] / ratio
                B[i, j] = [bx[0] / W, bx[1] / H, bx[2] / W, bx[3] / H, sc[k]]
                kp = pose[0, k]
                K[i, j, :, 0] = kp[:, 0] / ratio / W
                K[i, j, :, 1] = kp[:, 1] / ratio / H
                K[i, j, :, 2] = kp[:, 2]
        t_pose = time.time() - t1
        # audio
        t2 = time.time()
        y, sr = audio(path)
        feats = {"has_audio": float(len(y) > sr)}
        beats = np.zeros(0); downbeats = np.zeros(0)
        if len(y) > sr:
            rms = librosa.feature.rms(y=y)[0]
            feats["rms_db"] = float(20 * np.log10(np.median(rms) + 1e-9))
            oenv = librosa.onset.onset_strength(y=y, sr=sr)
            ac = librosa.autocorrelate(oenv - oenv.mean())
            ac = ac / (ac[0] + 1e-9)
            fr = sr / 512
            lo, hi = int(fr * 60 / 200), int(fr * 60 / 60)  # 60-200 BPM
            feats["pulse_clarity"] = float(ac[lo:hi].max()) if hi < len(ac) else 0.0
            flat = librosa.feature.spectral_flatness(y=y)[0]
            feats["flatness"] = float(np.median(flat))
            feats["librosa_s"] = time.time() - t2
            tmp = os.path.join(OUT, name + ".wav")
            import soundfile as sf
            sf.write(tmp, y, sr)
            try:
                beats, downbeats = f2b(tmp)
            except Exception as e:  # noqa: BLE001
                print("beat_this failed", name, e)
            os.unlink(tmp)
        t_audio = time.time() - t2
        np.savez_compressed(dest, K=K, B=B, fps=FPS, W=W, H=H, beats=np.asarray(beats), downbeats=np.asarray(downbeats),
                            audio=json.dumps(feats), timing=json.dumps({"decode": t_dec, "pose": t_pose, "audio": t_audio,
                                                                        "frames": len(frames)}))
        print(f"{name}: {len(frames)} frames decode {t_dec:.1f}s pose {t_pose:.1f}s audio {t_audio:.1f}s {feats}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
