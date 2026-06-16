"""Deterministic PDF timestamp pinning (FR-022 / FR-035).

reportlab's ``TimeStamp`` (reportlab.pdfbase.pdfdoc) reads ``SOURCE_DATE_EPOCH``
when present — the reproducible-builds convention — and otherwise falls back to
the build-host wall clock. The wall-clock path makes two consecutive renders
diverge in ``CreationDate`` / ``ModDate`` (and therefore the ``/ID`` digest),
breaking byte-equality. Setting ``canvas._doc.info.creationDate`` does *not*
help: ``PDFInfo.format`` derives the dates from ``document._timeStamp``, which is
captured at Canvas / document construction.

We pin the env-var to the operator's ``created_at_utc`` epoch for the duration of
the reportlab document construction, so PDFs are byte-identical across runs while
the metadata still reflects the manifest timestamp.
"""

from __future__ import annotations

import contextlib
import datetime
import os
from collections.abc import Iterator


def iso_utc_to_epoch(iso_utc: str) -> int:
    """Convert an ISO8601 UTC timestamp to a Unix epoch in whole seconds.

    Args:
        iso_utc: ISO8601 timestamp, e.g. ``"2026-04-27T00:00:00Z"``. A trailing
            ``Z`` or an explicit offset is accepted; a naive value is treated as
            UTC.

    Raises:
        ValueError: When ``iso_utc`` is empty or not a valid ISO8601 string.
    """
    if not isinstance(iso_utc, str) or not iso_utc:
        raise ValueError(f"created_at_utc must be a non-empty string, got {iso_utc!r}")
    normalized = iso_utc.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"created_at_utc is not a valid ISO8601 string: {iso_utc!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return int(dt.timestamp())


@contextlib.contextmanager
def pin_source_date_epoch(epoch: int) -> Iterator[None]:
    """Set ``SOURCE_DATE_EPOCH`` for the wrapped block, restoring it on exit.

    A reportlab document constructed inside the block pins its
    CreationDate/ModDate to ``epoch`` rather than the host clock.
    """
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(int(epoch))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous
