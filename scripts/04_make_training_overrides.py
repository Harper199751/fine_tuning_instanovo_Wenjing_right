#!/usr/bin/env python
"""Compute training-step overrides from the prepared split metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--train-batch-size", type=int, default=16)
    parser.add_argument("--grad-accumulation", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--min-steps", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--finetune-config")
    return parser.parse_args()


def write_finetune_config(path: Path, decoder_unfreeze_step: int, full_unfreeze_step: int) -> None:
    """Write a step-based finetuning schedule for InstaNovo 1.2.x."""
    path.write_text(
        "\n".join(
            [
                "unfreeze_format: start_step",
                "verbose: True",
                "unfreeze_schedule:",
                "  - start_step: 0",
                "    params:",
                "      - head.bias",
                "      - head.weight",
                "      - aa_embed.weight",
                f"  - start_step: {decoder_unfreeze_step}",
                "    params:",
                "      - decoder.*",
                f"  - start_step: {full_unfreeze_step}",
                "    params:",
                '      - "*"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    train_count = int(metadata["split_counts"]["train"])
    steps_per_epoch = max(1, train_count // args.train_batch_size)
    training_steps = max(args.min_steps, steps_per_epoch * args.epochs)
    warmup_iters = max(5, int(round(training_steps * 0.05)))
    validation_interval = steps_per_epoch
    checkpoint_interval = validation_interval
    decoder_unfreeze_step = steps_per_epoch
    full_unfreeze_step = steps_per_epoch * 2

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
    effective_batch_size = args.train_batch_size * args.grad_accumulation
    print(f"train_count={train_count}")
    print(f"train_batch_size={args.train_batch_size}")
    print(f"grad_accumulation={args.grad_accumulation}")
    print(f"effective_batch_size={effective_batch_size}")
    print(f"steps_per_epoch={steps_per_epoch}")
    print("\n".join(lines))
    if args.finetune_config:
        write_finetune_config(Path(args.finetune_config), decoder_unfreeze_step, full_unfreeze_step)
        print(f"Updated finetune schedule: {args.finetune_config}")


if __name__ == "__main__":
    main()
