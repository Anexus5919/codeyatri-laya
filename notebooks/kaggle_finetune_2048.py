# Kaggle notebook (script form): full fine-tune of Laya on our 2048 priority-reader labels.
# Runtime: GPU T4 x2 or P100. Data: attach the private Kaggle dataset built from data/ft2048.
# Uses only the official laya.train entry point. Output: /kaggle/working/laya-2048 checkpoint.

import json
import os
import subprocess
import sys
import time

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "laya==0.4.6"], check=True)

import torch  # noqa: E402

print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.device_count())

import glob  # noqa: E402

found = glob.glob("/kaggle/input/**/train.jsonl", recursive=True)
print("inputs:", os.listdir("/kaggle/input"), "train.jsonl at:", found)
DATA = os.path.dirname(found[0])
TRAIN_FULL = os.path.join(DATA, "train.jsonl")
HOLD = os.path.join(DATA, "holdout.jsonl")
OUT = "/kaggle/working/laya-2048"

# Time-bounded: the file is already shuffled, so the first ROWS rows are a random subset.
ROWS = int(os.environ.get("ROWS", "12000"))
TRAIN = "/kaggle/working/train_subset.jsonl"
with open(TRAIN_FULL, encoding="utf-8") as fin, open(TRAIN, "w", encoding="utf-8") as fout:
    for i, line in enumerate(fin):
        if i >= ROWS:
            break
        fout.write(line)

from laya.train import TrainConfig, finetune  # noqa: E402

cfg = TrainConfig(
    epochs=2,
    micro_batch=16,
    grad_accum=4,
    loss="soft-ce",          # hard true/false labels: plain cross-entropy is the documented choice
    label_smoothing=0.05,
    max_len=256,             # our state + question fit in about 160 tokens; halves the compute
    eval_data=HOLD,
    seed=0,
)
t0 = time.time()
report = finetune(TRAIN, "english", OUT, cfg)
print("minutes:", round((time.time() - t0) / 60, 1))
print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=1, default=str)[:4000])

# Quick sanity: ask the fine-tuned checkpoint one held-out question and compare with the label.
import laya  # noqa: E402

agent = laya.load(OUT)
row = json.loads(open(HOLD, encoding="utf-8").readline())
ans = agent.predict(row["state"], row["questions"])["answers"]
print({q: (round(a["noul"], 3), row["expected"][q]) for q, a in ans.items()})
