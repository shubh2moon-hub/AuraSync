"""Contact sheet of rendered packs (PC preview + phone preview side by side)."""
import os, sys
import cv2
import numpy as np

root = sys.argv[1] if len(sys.argv) > 1 else "drafts"
out = sys.argv[2]
names = sys.argv[3:] or sorted(os.listdir(root))
rows = []
for n in names:
    pc = cv2.imread(os.path.join(root, n, "pc_preview.jpg"))
    ph = cv2.imread(os.path.join(root, n, "phone_preview.jpg"))
    H = 300
    pc = cv2.resize(pc, (int(pc.shape[1] * H / pc.shape[0]), H))
    ph = cv2.resize(ph, (int(ph.shape[1] * H / ph.shape[0]), H))
    row = np.concatenate([pc, np.zeros((H, 8, 3), np.uint8), ph], 1)
    cv2.putText(row, n, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    rows.append(row)
W = max(r.shape[1] for r in rows)
rows = [np.pad(r, ((0, 8), (0, W - r.shape[1]), (0, 0))) for r in rows]
cv2.imwrite(out, np.concatenate(rows, 0), [cv2.IMWRITE_JPEG_QUALITY, 85])
