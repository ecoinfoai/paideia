"""retro_mester.llm — optional LLM insight layer for retro-mester (US6 T053–T055).

Public surface:
- ``client.generate(prompt, *, mode)`` — backend abstraction (lazy imports).
- ``fallback.template_insight(facts)`` — deterministic Korean fallback.
- ``cache.InputHashCache`` — SHA-256 content-addressed response cache.
- ``insight.build_insight(facts, ...)`` — orchestration (mode dispatch).
- ``insight.LLMRequiredError`` — raised when require_llm=True and LLM fails.
"""
