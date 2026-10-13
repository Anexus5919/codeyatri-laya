# Laya research notes

Researched on 2026-10-13 against laya 0.4.6. Every claim is tagged:

- **[verified]** we read it in the installed source or reproduced it on our machine
- **[upstream]** stated by the maintainers, not yet reproduced by us
- **[open]** unknown until the organisers or further tests answer it

## 1. Sources

| Source | Used for |
|---|---|
| https://github.com/NandhaKishorM/laya | README, install, API overview, known issues, fine-tuning links |
| https://nandhakishorm.github.io/laya/ | Docs index, questions-and-answers, routing, Agent and Router reference, fine-tuning, benchmarks |
| https://huggingface.co/convaiinnovations/laya | Model card: checkpoints, architecture, limitations, license |
| https://pypi.org/project/laya/ | Package version (0.4.6), Python requirement, extras |
| https://laya.studio/docs/questions | Request limits (32 questions, 64 options), question-writing guidance |
| Installed package `.venv/Lib/site-packages/laya/` | Ground truth for the API, question validation, encoding and output shape |
| https://github.com/Okbatti/SnakeGame_Laya | Community precedent: base vs fine-tuned Laya on Snake |
| https://github.com/mizorewww/laya-mlx | Community precedent: Snake demo with a separate safety layer |

## 2. Identity and licensing

- Source repository and docs: GitHub account `NandhaKishorM` (Nandha Kishor M). **[verified]**
- Published checkpoints: Hugging Face organisation `convaiinnovations` (ConvAI Innovations). **[verified]**
- PyPI package `laya`, version 0.4.6. The metadata author field is empty. **[verified]**
- Code license: Apache-2.0 (package metadata and repository LICENSE). Model card also states Apache 2.0 for the weights. **[verified for code, upstream for weights]**
- Hosted options exist (Laya Studio API, a gateway listing) but the problem statement says Laya is installed via pip, so we run it locally. **[verified]**

## 3. What Laya is and is not

- A non-autoregressive decision model: it takes a **state** plus **typed questions** and returns probabilities in one forward pass. It never generates text. **[verified]**
- Three question types: `choice` (pick one label), `score` (ordinal level), `noul` (P(true)). **[verified in source]**
- It is not a planner, search engine or game engine. It reads the text we give it and scores the options we give it. Anything it should weigh must be in the state or option text. **[verified by design]**

## 4. Installation (verified on this laptop)

```
python -m venv .venv
.venv\Scripts\python -m pip install laya==0.4.6 requests
```

Resolved on Windows 11, Python 3.12.3: laya 0.4.6, torch 2.14.1+cpu, transformers 5.19.0, huggingface_hub 2.2.0. **[verified]**

- The default Windows torch wheel is CPU-only (`torch.cuda.is_available() == False`). GPU inference needs the CUDA torch wheel from pytorch.org installed into the same venv. **[verified]**
- First use downloads the checkpoint into the Hugging Face cache (English: 5 files, about 0.8 GB, 3 min 51 s on this connection), then loads it. Later runs load from cache. **[verified]**

## 5. Python API (read from the installed source)

```python
from laya import Router
router = Router(device=None, max_loaded=2, default="multilingual")
agent = router.load("english")                   # build once, reuse
result = router.predict(state, questions, model="english", head_max_len=None, max_len=None, min_confidence=None)
```

- `model=` forces a checkpoint (`english`, `multilingual`, `typed-decisions`, or a registered custom name). Without it the router guesses from the language; the default fallback is `multilingual`. We always pass `model=` so routing is explicit and logged. **[verified]**
- `router.register(name, path)` adds a local or Hub checkpoint, for example a fine-tuned one. **[verified]**
- Question validation (`Agent._check_question`): `instructions` is required and non-empty; `choice` takes `criteria` as a dict `label -> description` or a list of labels; labels must be unique scalars; `score` takes an ordered list; `noul` takes optional `criteria` keyed only `true`/`false`; `option_order` must be a permutation of the option indices. **[verified]**
- `state` may be a string, dict or list. Dicts and lists are serialised with `json.dumps`. **[verified]**

### Output shape (from our smoke test, docs/evidence/smoke_english_cpu.json)

```json
{
  "model": "laya-rl-agent",
  "answers": {"move": {"type": "choice", "choice": "left",
    "probabilities": {"up": 0.1839, "down": 0.2509, "left": 0.4169, "right": 0.1483},
    "confidence": 0.0578, "answer_confidence": 0.4169, "action": {"act_probability": 1.0}}},
  "usage": {"input_tokens": 116, "output_tokens": 0, "state_tokens": 35, "state_tokens_dropped": 0,
            "truncated": false, "truncated_questions": []},
  "routing": {"model": "english", "repo": "convaiinnovations/laya", "reason": "explicit model='english'",
              "detection": null, "workflow": null}
}
```

- `choice` is the argmax computed **before** rounding; `probabilities` are rounded to 4 decimals. We read `choice` directly and never re-derive the winner from rounded numbers. **[verified]**
- `answer_confidence` is max(p). `confidence` is 1 minus normalised entropy for `choice`. **[verified]**
- `action.act_probability` has no usable signal per upstream issue #185, so we ignore it. **[upstream]**
- `usage.options` appears only when options collapsed into identical token spans; we treat that as a validation failure. **[verified]**

## 6. How the input is encoded, and the limits that matter

Sequence per question (`common.build_sequence`): **[verified]**

```
[CLS] choice question: <instructions> [SEP] [MASK] label: description [MASK] label: description ... [SEP] <state> [SEP]
```

- Each option (`" label: description"`) is cut to **48 tokens**.
- Options and instructions share `head_max_len` (192 on the English checkpoint). If the options need more than `head_max_len - 16`, every option is cut equally. **The instructions only get what the options leave (minimum 8 tokens)**, and nothing in `usage` reports that. Our decider computes this with laya's own `build_head` and logs `usage.head_budget`.
- The state gets `max_len - head - 1` tokens (512 total on English) and is cut from the end (from the start for lists). `usage.truncated` reports it.
- Limits: 32 questions per request and 64 options per question on the hosted API; accuracy degrades past about 20 options; `predict_shortlist` and `predict_tournament` exist for large action sets. **[upstream]**
- Loading the English checkpoint prints: *"this checkpoint ships invalid temperatures ... choice:11+ ... Treat confidence from the affected entries as uncalibrated."* So confidence on choice questions with 11 or more options is not calibrated. **[verified]**

## 7. Checkpoints

| Name | Backbone | Params | Context | Notes |
|---|---|---|---|---|
| `english` (repo root) | ModernBERT-large | 421M | 512 | Default for English |
| `multilingual` | mmBERT-base | 322M | 1024 | Faster per question on T4; router default |
| `typed-decisions` | ModernBERT-large | 421M | 1024 | Fine-tuned on four business workflows |

Sizes and speeds are **[upstream]** except the English checkpoint, which we downloaded and timed.

## 8. Measured in our environment (CPU, i5-12450HX)

| Measure | Result |
|---|---|
| `import laya` | 1.3 s |
| First load incl. download | 237 s |
| First predict | 420 ms |
| Warm predict, 1 question, 4 options, p50 / max over 10 | 395 ms / 449 ms |
| Same input twice | identical probabilities (deterministic) |
| Same options in reversed order | answer flipped from `left` to `right` |

Upstream reports about 33 to 40 ms per question on a T4 GPU and 193 to 464 ms on CPU. Our CPU number sits inside that range. **[verified for CPU, upstream for GPU]**

## 9. Failure modes that matter for games

1. **Zero-shot weakness.** Base checkpoints score 0.362 on the typed-decisions benchmark against 0.318 random and 0.461 majority class. **[upstream]** On Snake, base Laya averaged 0.4 points against 1.5 for random play, while a fine-tuned copy averaged 89.9. **[community]**
2. **Our first probe failed the same way.** Asked to reach the coin fastest, base Laya gave the *correct* option (`right: closer to the coin`) the lowest probability. **[verified]**
3. **Position bias.** Reversing option order flipped the answer. **[verified]** Upstream documents `option_order` for averaging this out.
4. **Label-following.** Boolean-like labels (`yes`/`no`, `true`/`false`) and negations can be followed instead of the descriptions; neutral labels help. **[upstream]**
5. **Over-confidence.** Shipped checkpoints are over-confident; confidence orders decisions but does not prove correctness. **[upstream]**
6. **Many options.** Accuracy drops past about 20 options, and the shared head budget truncates option text. **[upstream + verified mechanism]**

## 10. Fine-tuning

- Official path: `laya-train` CLI or `laya.train.finetune(data, base, out, TrainConfig(...))`. JSONL rows hold `state`, `questions` and `expected` (or `gold` soft probabilities). It holds out a calibration slice and fits one temperature per question type. **[upstream]**
- Hardware: Kaggle 2xT4 notebook in the repo; any single CUDA, MPS or CPU device works, slower. The browser-agent fine-tune took about 1 to 2 hours on one 16 GB GPU and moved element accuracy from 0.10 to 0.66. **[upstream]**
- The Snake fine-tune used labels from a scripted teacher and 41 minutes on a Colab T4. **[community]**

| Option | Benefit | Cost and risk | Relevance |
|---|---|---|---|
| A. Pretrained Laya | No training; fully within the rules | Near chance zero-shot on decisions | Baseline only |
| B. Better question design | Cheap, fast to iterate, measurable | Ceiling set by the base model's reading ability | Main lever on hackathon day |
| C. Fine-tuned Laya | Large gains in every published precedent | Needs labelled states, GPU hours, and organiser approval | Only if permitted and time allows |
| D. B plus C | Best expected score | Highest effort | If stage 1 shows B is not enough |

Whether a fine-tuned Laya counts as "Laya", and whether offline labels from a script may be used, is **[open]**. See section 12.

## 11. Compliance line we hold ourselves to

- Python computes **facts** (legal moves, distances, threats, what a move would change) and states the game's **general priorities** once per game.
- Python never says which candidate is best, never prunes legal moves by preference, and never overrides Laya's answer.
- The move is always Laya's `choice`, or one of two logged aggregates of Laya's own probabilities (mean over option orders, or the highest per-move P(true)) asked in the same forward pass.
- If Laya fails or its answer does not map to a legal move, the bot logs it and pauses. There is no fallback policy anywhere in `src/`.

## 12. Questions for the organisers

1. Is a fine-tuned Laya checkpoint allowed, and may training labels come from our own scripts or from game outcomes?
2. Are several typed questions per move, or averaging Laya's probabilities over option orders, acceptable as "a logged Laya call"?
3. May Python remove moves that the rules make immediately losing (for example walking into a wall that ends the game), or must every legal move be offered?
4. Which checkpoints are allowed (`english`, `multilingual`, `typed-decisions`, community fine-tunes)?
5. Must inference run on our own machine or Colab, or is a hosted Laya endpoint acceptable?
6. How are runs verified: does the server record moves per session, or do we submit our logs? What identifies a session?
7. Rate limits, per-move time limits, and whether the Doom-style stage is real time.
8. What the Doom-style stage exposes as state: structured fields, or pixels? (Laya reads text only, and no other model may be used.)
