"""T042 — Deterministic Korean markdown narrative template for metric-codex.

Pure offline function: renders a StudentBundle into a Korean markdown document.
No LLM call, no I/O, no PII (the bundle is already pseudonymized).

EVID-01: every factual value carries a citation.
EVID-02: when no evidence, emits the literal '근거 없음'.
EVID-03: the bundle is the sole context (no external data read here).

Callers set ``rendered_by="template"`` on the QueryAnswer they attach to the
Gold output; this module does not modify the bundle.
"""

from __future__ import annotations

import math

from metric_codex.generate.bundle import StudentBundle


def _format_value(value: float | str) -> str:
    """Format a citation value for markdown, integer-collapsing finite floats.

    A finite float equal to its floor renders without a trailing ``.0``
    (``85.0`` → ``85``); other finite floats render via ``%g``.  Non-finite
    floats (``nan``/``inf``/``-inf``) and strings render through ``str`` — the
    formatter never evaluates ``int()``/``==`` on a non-finite float (which
    would raise).

    Args:
        value: The numeric or text value from an EvidenceCitation.

    Returns:
        A display string suitable for inline markdown.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        if value == math.floor(value):
            return f"{value:g}"
        return str(value)
    return str(value)


def render_template(bundle: StudentBundle) -> str:
    """Render a deterministic Korean markdown narrative from a StudentBundle.

    For each BundleQuestion:
    - Emits a Markdown heading from ``question_text``.
    - If ``answer.no_evidence``: emits the literal '근거 없음' (EVID-02).
    - Otherwise: one cited bullet per EvidenceCitation in the format
      ``- {key}: {value} (출처: {source_id}, {layer})`` (EVID-01).

    Korean framing sentences are minimal and contain no uncited factual claims.

    Args:
        bundle: A pseudonymized StudentBundle (PII-free by construction).

    Returns:
        Deterministic Korean Markdown string.  Two calls with the same bundle
        always return the identical string.
    """
    lines: list[str] = []

    for bq in bundle.questions:
        # Heading from question_text.
        lines.append(f"## {bq.question_text}")
        lines.append("")

        if bq.answer.no_evidence:
            lines.append("근거 없음")
        else:
            for citation in bq.answer.citations:
                value_str = _format_value(citation.value)
                lines.append(
                    f"- {citation.key}: {value_str} (출처: {citation.source_id}, {citation.layer})"
                )

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_template"]
