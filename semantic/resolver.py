"""Matches a Persian business question against the semantic layer.

Deliberately simple for the MVP: substring matching against aliases_fa
and the English key/name, not embeddings. It only needs to narrow down
which metric/dimension definitions to inject into the SQL prompt so the
model stops guessing formulas like "profit" or join paths like "region".

If nothing matches, callers should fall back to the full metric list -
better to over-inform the prompt than silently omit a metric the
question actually needed.
"""

from dataclasses import dataclass

from semantic.loader import DimensionDef, MetricDef, SemanticLayer, load_semantic_layer


@dataclass
class ResolvedContext:
    metrics: list[MetricDef]
    dimensions: list[DimensionDef]

    def render(self) -> str:
        lines = ["Relevant business metrics:", ""]

        for metric in self.metrics:
            computable_note = "" if metric.computable else " (NOT directly computable - explain this to the user instead of guessing SQL)"
            lines.append(f"- {metric.key} ({metric.name}): {metric.expression}{computable_note}")

        lines.append("")
        lines.append("Relevant dimensions:")
        lines.append("")

        for dimension in self.dimensions:
            join = " -> ".join(dimension.join_path) if dimension.join_path else dimension.column
            lines.append(f"- {dimension.key}: column {dimension.column}, join path: {join}")

        return "\n".join(lines)


def _matches(question: str, term: str) -> bool:
    return term.lower() in question.lower()


def resolve_metrics(question: str, layer: SemanticLayer | None = None) -> ResolvedContext:

    layer = layer or load_semantic_layer()

    matched_metrics = [
        metric
        for metric in layer.metrics.values()
        if _matches(question, metric.key)
        or _matches(question, metric.name)
        or any(_matches(question, alias) for alias in metric.aliases_fa)
    ]

    matched_dimensions = [
        dimension
        for dimension in layer.dimensions.values()
        if _matches(question, dimension.key)
        or any(_matches(question, alias) for alias in dimension.aliases_fa)
    ]

    # Nothing matched - don't leave the SQL generator blind. Fall back to
    # the full metric/dimension list rather than an empty context.
    if not matched_metrics:
        matched_metrics = list(layer.metrics.values())

    if not matched_dimensions:
        matched_dimensions = list(layer.dimensions.values())

    return ResolvedContext(metrics=matched_metrics, dimensions=matched_dimensions)


if __name__ == "__main__":

    examples = [
        "سود منطقه تهران در سال ۲۰۲۵ چقدر بود؟",
        "میانگین قیمت واحد محصولات چقدر است؟",
        "فروش هر مدیر را نشان بده",
    ]

    for question in examples:
        context = resolve_metrics(question)
        print(f"Q: {question}")
        print(f"  matched metrics: {[m.key for m in context.metrics]}")
        print(f"  matched dims:    {[d.key for d in context.dimensions]}")
