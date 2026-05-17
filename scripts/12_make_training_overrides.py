#!/usr/bin/env python
"""Compute training-step overrides from the prepared split metadata."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--effective-batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--min-steps", type=int, default=0)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    train_count = int(metadata["split_counts"]["train"])
    steps_per_epoch = max(1, math.ceil(train_count / args.effective_batch_size))
    training_steps = max(args.min_steps, steps_per_epoch * args.epochs)
    warmup_iters = max(5, int(round(training_steps * 0.05)))
    validation_interval = steps_per_epoch
    checkpoint_interval = validation_interval

    lines = [
        f"training_steps={training_steps}",
        f"warmup_iters={warmup_iters}",
        f"validation_interval={validation_interval}",
        f"checkpoint_interval={checkpoint_interval}",
        f"console_logging_steps={max(5, validation_interval // 4)}",
        f"tensorboard_logging_steps={max(5, validation_interval // 4)}",
    ]
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
