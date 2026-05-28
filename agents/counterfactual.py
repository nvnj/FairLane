"""Deterministic counterfactual generator: sweeps one protected attribute at a time, holding all legitimate features byte-identical."""

from __future__ import annotations

import copy

from data.schema import LEGITIMATE, PROTECTED, ApplicationRecord


def make_counterfactuals(app: ApplicationRecord) -> list[dict]:
    """Generate one variant per protected-attribute value, sweeping one attribute at a time.

    Invariant #3: sweeps ONE attribute at a time. Total variants ==
    sum(len(values) for values in PROTECTED.values()). No cross-product.

    Each variant dict contains:
      - all LEGITIMATE keys (byte-identical copy of app.legitimate)
      - all PROTECTED keys (others held at app.protected values)
      - "swept_attribute": which attribute is being swept
      - "swept_value": the value being tested for that attribute
    """
    variants: list[dict] = []

    for attr, possible_values in PROTECTED.items():
        for value in possible_values:
            # Deep-copy legitimate features so no variant shares a reference
            variant: dict = copy.deepcopy(app.legitimate)

            # Copy ALL protected fields at their baseline values
            for other_attr in PROTECTED:
                variant[other_attr] = app.protected.get(other_attr)

            # Override only the attribute being swept
            variant[attr] = value
            variant["swept_attribute"] = attr
            variant["swept_value"] = value

            variants.append(variant)

    return variants
