"""RoBERTa sentiment analysis on Korean freetext responses [T054].

US6 Stage A — kote_for_easygoing_people (44 emotion labels, multi-label
sigmoid). Per spec FR-026 + research §R-02 / §R-12:

- ``negativity`` ∈ [0, 1] = mean of sigmoid probabilities over the 16
  fixed negative-label subset (``NEGATIVE_LABELS``).
- ``top_emotion`` = argmax over all 44 labels (id2label).
- Determinism: CPU only, ``torch.set_num_threads(1)``,
  ``torch.use_deterministic_algorithms(True)``, ``model.eval()`` +
  ``torch.no_grad()``, ``torch_dtype=torch.float32``,
  ``padding='max_length'`` + ``truncation=True`` + ``max_length=512``.
- Model + tokenizer sha256 computed once at first load and cached on
  the result objects so the manifest can pin them.

If the optional ``roberta`` extra is not installed (torch / transformers
missing), :func:`analyze_sentiment` raises ``RobertaUnavailableError``;
the caller (T055 ``roberta_fallback``) catches that to route to the
fallback branch.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

# 16 negative labels from the kote_for_easygoing_people 44-label vocabulary
# (research §R-02). Pinned at import time so two runs with the same model
# produce identical negativity scores.
NEGATIVE_LABELS: tuple[str, ...] = (
    "걱정/불안",
    "두려움/무서움",
    "막막함",
    "슬픔",
    "후회",
    "당혹/난처",
    "분노",
    "역겨움",
    "절망",
    "외로움",
    "비웃음",
    "한심함",
    "혐오",
    "짜증",
    "안타까움/실망",
    "우울",
)


class RobertaUnavailableError(RuntimeError):
    """Raised when torch / transformers / kote model cache is missing.

    ``free_text/roberta_fallback.py`` catches this to route the pipeline
    into the dictionary-only fallback (FR-026); manifest records the
    fallback reason.
    """


@dataclass(frozen=True)
class SentimentResult:
    """Per-text sentiment + identity fingerprints for the manifest.

    All probability fields fall back to ``None`` when analysis was
    skipped (empty text, fallback path); the schema treats those as
    explicit missing rather than zero.
    """

    negativity: float | None = None
    top_emotion: str | None = None
    all_scores: dict[str, float] | None = None
    model_id: str | None = None
    model_sha256: str | None = None
    tokenizer_vocab_sha256: str | None = None
    tokens: list[dict[str, object]] = field(default_factory=list)


def analyze_sentiment(
    texts: list[str],
    *,
    model_id: str = "searle-j/kote_for_easygoing_people",
) -> list[SentimentResult]:
    """Run the kote 44-label classifier on each non-empty text.

    Args:
        texts: List of Korean strings (already redacted by the caller via
            ``free_text/redaction.py``). Empty strings produce a missing
            ``SentimentResult`` (negativity=None, top_emotion=None).
        model_id: Hugging Face hub identifier; default
            ``searle-j/kote_for_easygoing_people``.

    Returns:
        ``list[SentimentResult]`` aligned to ``texts`` (same length,
        same order).

    Raises:
        RobertaUnavailableError: If torch / transformers are missing or
            the model cannot be loaded (network unavailable + cache miss).
    """
    try:
        import torch  # type: ignore[import-not-found]
        from transformers import (  # type: ignore[import-not-found]
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )
    except ImportError as exc:
        raise RobertaUnavailableError(
            "torch / transformers not installed — install via `uv sync "
            "--extra roberta --package needs-map` or run with --no-roberta."
        ) from exc

    try:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
    except (RuntimeError, AttributeError):  # noqa: S110
        # Some deterministic algorithms are unavailable in older torch
        # versions. The CPU + single-thread + float32 path is already the
        # dominant determinism axis; the strict flag is best-effort.
        pass

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_id, torch_dtype=torch.float32
        )
    except (OSError, RuntimeError) as exc:
        raise RobertaUnavailableError(
            f"could not load {model_id!r} — model cache missing and offline. "
            "Run with --no-roberta or pre-download the weights via "
            "`huggingface-cli download searle-j/kote_for_easygoing_people`."
        ) from exc

    model.eval()
    model_sha256 = _model_sha256(model)
    tokenizer_sha256 = _tokenizer_vocab_sha256(tokenizer)
    id2label: dict[int, str] = model.config.id2label
    label_to_idx = {label: idx for idx, label in id2label.items()}
    negative_indices = [
        label_to_idx[label] for label in NEGATIVE_LABELS if label in label_to_idx
    ]

    results: list[SentimentResult] = []
    for text in texts:
        if not text or not text.strip():
            results.append(SentimentResult())
            continue
        encoded = tokenizer(
            text,
            return_tensors="pt",
            padding="max_length",
            truncation=True,
            max_length=512,
            return_offsets_mapping=True,
        )
        offsets = encoded.pop("offset_mapping")[0].tolist()
        input_ids = encoded["input_ids"][0].tolist()
        with torch.no_grad():
            logits = model(**encoded).logits[0]
        probabilities = torch.sigmoid(logits).cpu().tolist()
        all_scores = {id2label[i]: float(p) for i, p in enumerate(probabilities)}
        if negative_indices:
            negativity = float(
                sum(probabilities[i] for i in negative_indices) / len(negative_indices)
            )
        else:
            negativity = 0.0
        top_idx = int(max(range(len(probabilities)), key=lambda i: probabilities[i]))
        top_emotion = id2label[top_idx]

        tokens: list[dict[str, object]] = []
        # Build per-token rows for the freetext audit (T056).
        for idx, (token_id, (char_start, char_end)) in enumerate(
            zip(input_ids, offsets, strict=True)
        ):
            if char_start == 0 and char_end == 0:
                # Special token (CLS/SEP/PAD) — exclude from audit.
                continue
            token_text = tokenizer.decode([token_id]).strip()
            if not token_text:
                continue
            tokens.append(
                {
                    "token_index": idx,
                    "token_id": int(token_id),
                    "token_text": token_text,
                    "char_start": int(char_start),
                    "char_end": int(char_end),
                }
            )

        results.append(
            SentimentResult(
                negativity=negativity,
                top_emotion=top_emotion,
                all_scores=all_scores,
                model_id=model_id,
                model_sha256=model_sha256,
                tokenizer_vocab_sha256=tokenizer_sha256,
                tokens=tokens,
            )
        )
    return results


def negative_label_subset_sha256() -> str:
    """sha256 of the canonical NEGATIVE_LABELS list — pinned in manifest.

    Caller (T061) writes this into ``manifest.sentiment``. Two runs that
    share the same negative-label subset reproduce the same sha256, so a
    label-set drift surfaces immediately.
    """
    payload = "\n".join(NEGATIVE_LABELS).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _model_sha256(model: object) -> str:
    """sha256 over the model's state_dict bytes — best-effort fingerprint.

    Uses a stable iteration order (sorted parameter names) so two loads
    of the same checkpoint yield the same hash.
    """
    import torch  # type: ignore[import-not-found]

    h = hashlib.sha256()
    state = model.state_dict()  # type: ignore[attr-defined]
    for name in sorted(state):
        tensor = state[name].detach().cpu().to(torch.float32)
        h.update(name.encode("utf-8"))
        h.update(tensor.numpy().tobytes())
    return h.hexdigest()


def _tokenizer_vocab_sha256(tokenizer: object) -> str:
    """sha256 over the tokenizer's vocab — vocab change detection."""
    vocab = tokenizer.get_vocab()  # type: ignore[attr-defined]
    payload = "\n".join(f"{tok}\t{idx}" for tok, idx in sorted(vocab.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _vocab_path_sha256(path: Path) -> str:
    """Convenience helper for tests that want to verify against a file path."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "NEGATIVE_LABELS",
    "RobertaUnavailableError",
    "SentimentResult",
    "_vocab_path_sha256",
    "analyze_sentiment",
    "negative_label_subset_sha256",
]
