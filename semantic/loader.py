"""Loads semantic/metrics.yaml into typed objects.

This is the only place that should ever read the YAML file - everything
else (resolver, prompts) works against MetricDef/DimensionDef.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

METRICS_PATH = Path(__file__).parent / "metrics.yaml"


@dataclass
class MetricDef:
    key: str
    name: str
    description: str
    expression: str
    type: str
    requires_tables: list[str] = field(default_factory=list)
    aliases_fa: list[str] = field(default_factory=list)
    computable: bool = True


@dataclass
class DimensionDef:
    key: str
    column: str
    type: str
    join_path: list[str] = field(default_factory=list)
    aliases_fa: list[str] = field(default_factory=list)


@dataclass
class SemanticLayer:
    metrics: dict[str, MetricDef]
    dimensions: dict[str, DimensionDef]


def load_semantic_layer(path: Path = METRICS_PATH) -> SemanticLayer:

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    metrics = {}
    for key, definition in (raw.get("metrics") or {}).items():
        metrics[key] = MetricDef(
            key=key,
            name=definition["name"],
            description=definition.get("description", ""),
            expression=definition["expression"],
            type=definition.get("type", "number"),
            requires_tables=definition.get("requires_tables", []),
            aliases_fa=definition.get("aliases_fa", []),
            computable=definition.get("computable", True),
        )

    dimensions = {}
    for key, definition in (raw.get("dimensions") or {}).items():
        dimensions[key] = DimensionDef(
            key=key,
            column=definition["column"],
            type=definition.get("type", "string"),
            join_path=definition.get("join_path", []),
            aliases_fa=definition.get("aliases_fa", []),
        )

    return SemanticLayer(metrics=metrics, dimensions=dimensions)


if __name__ == "__main__":

    layer = load_semantic_layer()

    print(f"{len(layer.metrics)} metrics, {len(layer.dimensions)} dimensions")

    for metric in layer.metrics.values():
        print(f"- {metric.key}: {metric.expression}")
