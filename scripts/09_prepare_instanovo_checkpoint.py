#!/usr/bin/env python
"""Download an InstaNovo pretrained model and save a trainer-compatible checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import torch
from omegaconf import DictConfig, ListConfig, OmegaConf

from instanovo.transformer.model import InstaNovo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="instanovo-v1.2.0")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def to_plain_config(config: Any) -> dict[str, Any]:
    if isinstance(config, (DictConfig, ListConfig)):
        return OmegaConf.to_container(config, resolve=True)
    if isinstance(config, dict):
        return config
    raise TypeError(f"Unsupported InstaNovo config type: {type(config)!r}")


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists() and output.stat().st_size > 0:
        print(f"Checkpoint already exists: {output}")
        return

    model, model_config = InstaNovo.from_pretrained(args.model_id)
    config = to_plain_config(model_config)

    # The 1.2.x trainer expects nested residues when loading a fine-tune resume
    # checkpoint; prediction checkpoints produced by training remain flat.
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": config,
            "residues": {"residues": dict(model.residue_set.residue_masses)},
        },
        output,
    )
    print(f"Saved trainer-compatible checkpoint: {output}")


if __name__ == "__main__":
    main()
