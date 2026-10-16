# Kaggle notebook (script form): full fine-tune of Laya on our Doom priority-reader labels.
# Runtime: GPU T4 or P100. Data: attach the private Kaggle dataset built by scripts/make_doom_dataset.py.
# Uses only the official laya.train entry point. Output: /kaggle/working/laya-doom checkpoint.
# ROWS and EPOCHS below set the run size (the quick run uses a subset, the full run uses everything).

import glob
import json
import os
import subprocess
import sys
import time

ROWS = int(os.environ.get("ROWS", "1000000000"))
EPOCHS = int(os.environ.get("EPOCHS", "3"))
EVAL_ROWS = 600

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "laya==0.4.6"], check=True)

import torch  # noqa: E402

print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.device_count(),
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")

found = glob.glob("/kaggle/input/**/train.jsonl", recursive=True)
print("inputs:", os.listdir("/kaggle/input"), "train.jsonl at:", found)
DATA = os.path.dirname(found[0])
OUT = "/kaggle/working/laya-doom"


def head(src, dst, n):
    with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8") as fout:
        for i, line in enumerate(fin):
            if i >= n:
                break
            fout.write(line)
    return dst


# The files are already shuffled, so the first rows are a random subset
TRAIN = head(os.path.join(DATA, "train.jsonl"), "/kaggle/working/train_subset.jsonl", ROWS)
HOLD = head(os.path.join(DATA, "holdout.jsonl"), "/kaggle/working/holdout_subset.jsonl", EVAL_ROWS)

from laya.train import TrainConfig, finetune  # noqa: E402

cfg = TrainConfig(
    epochs=EPOCHS,
    micro_batch=16,
    grad_accum=4,
    loss="soft-ce",
    label_smoothing=0.05,
    max_len=256,
    eval_data=HOLD,
    seed=0,
)
t0 = time.time()
report = finetune(TRAIN, "english", OUT, cfg)
print("minutes:", round((time.time() - t0) / 60, 1))
print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=1, default=str)[:4000])

import laya  # noqa: E402

agent = laya.load(OUT)
agree = total = 0
with open(HOLD, encoding="utf-8") as fh:
    for i, line in enumerate(fh):
        if i >= 200:
            break
        row = json.loads(line)
        ans = agent.predict(row["state"], row["questions"])["answers"]
        p = {q: a["noul"] for q, a in ans.items()}
        pick = max(p, key=p.get)
        agree += bool(row["expected"][pick])
        total += 1
print(f"held-out decisions where Laya's top action is one the reader marks good: {agree}/{total}")
