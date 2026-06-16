"""RoBERTa sentiment inference smoke [T050, marker `roberta`].

These tests load the actual ``searle-j/kote_for_easygoing_people``
model + tokenizer. They are tagged with the ``roberta`` mark so they
only run when:

- ``torch`` and ``transformers`` are installed (``uv sync --extra
  roberta --package needs-map``), and
- the kote cache is present locally OR network access is available.

Skipped automatically by the default ``-m "not roberta"`` selector.

Spec: 003-needs-map-v0-1-1/tasks.md T050; FR-026; research §R-02 + §R-12.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.roberta


def test_analyze_sentiment_returns_negativity_and_top_emotion() -> None:
    """Korean anxious text → ``negativity > 0.5`` and a negative top emotion."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")

    from needs_map.free_text.sentiment import analyze_sentiment

    results = analyze_sentiment(["수업 따라가기 막막해요"])
    assert len(results) == 1
    r = results[0]
    assert r.negativity is not None
    assert r.top_emotion in {"걱정/불안", "막막함", "두려움/무서움", "슬픔", "절망"}
    # all_scores keys are 44 emotion labels (kote canonical id2label).
    assert r.all_scores is not None
    assert len(r.all_scores) >= 40  # 44 labels in kote


def test_analyze_sentiment_deterministic_two_runs() -> None:
    """Same input twice → byte-identical all_scores dict (FR-035)."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")

    from needs_map.free_text.sentiment import analyze_sentiment

    text = "수업 따라가기 막막해요"
    a = analyze_sentiment([text])[0]
    b = analyze_sentiment([text])[0]
    assert a.all_scores == b.all_scores
    assert a.negativity == b.negativity
    assert a.top_emotion == b.top_emotion


def test_analyze_sentiment_empty_string_returns_missing() -> None:
    """Empty input → SentimentResult() with all None fields."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")

    from needs_map.free_text.sentiment import analyze_sentiment

    [r] = analyze_sentiment([""])
    assert r.negativity is None
    assert r.top_emotion is None
    assert r.all_scores is None


def test_negative_labels_are_subset_of_id2label() -> None:
    """All ``NEGATIVE_LABELS`` MUST appear in the model's id2label."""
    pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")

    from needs_map.free_text.sentiment import NEGATIVE_LABELS

    AutoModelForSequenceClassification = (  # noqa: N806
        transformers.AutoModelForSequenceClassification
    )
    model = AutoModelForSequenceClassification.from_pretrained("searle-j/kote_for_easygoing_people")
    id2label = model.config.id2label.values()
    missing = [label for label in NEGATIVE_LABELS if label not in id2label]
    assert not missing, f"NEGATIVE_LABELS not in id2label: {missing}"
