"""Move clips with no video stream (audio-only Commons files) out of the test set."""
import glob, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
os.makedirs(os.path.join(DATA, "clips", "bad"), exist_ok=True)
for p in glob.glob(os.path.join(DATA, "clips", "*", "*.mp4")):
    if "/bad/" in p:
        continue
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
                        "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    if not o:
        print("bad", p)
        os.rename(p, os.path.join(DATA, "clips", "bad", os.path.basename(p)))
