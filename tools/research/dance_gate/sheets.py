"""Contact sheets (4 frames per clip, 6 clips per sheet) for eyeballing labels."""
import glob, os, sys
import numpy as np, cv2
from extract_a import decode
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DANCE_GATE_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
label = sys.argv[1]
paths = sorted(glob.glob(os.path.join(DATA, "clips", label, "*.mp4")))
rows = []
for p in paths:
    fr, W, H = decode(p, fps=1, long=160)
    idx = np.linspace(0, len(fr) - 1, 4).astype(int)
    tiles = [cv2.resize(fr[i], (160, 160)) for i in idx]
    row = np.hstack(tiles)
    cv2.putText(row, os.path.basename(p)[:48], (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    rows.append(row)
os.makedirs(os.path.join(DATA, "sheets"), exist_ok=True)
for k in range(0, len(rows), 8):
    cv2.imwrite(os.path.join(DATA, "sheets", f"{label}_{k // 8}.jpg"), np.vstack(rows[k:k + 8]))
print(len(rows))
