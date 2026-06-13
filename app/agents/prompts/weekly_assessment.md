Create a weekly assessment quiz for {{ name }} covering these recently-studied topics:
{{ topics }}

Difficulty: {{ difficulty }}.

Rules:
- 6–8 multiple-choice questions, spread across the listed topics (don't over-weight one).
- Each: exactly 4 options, correct_index 0-based, a 1–3 sentence teaching explanation.
- Mix recall, code-reading ("what does this print?"), and one application/transfer question.
- Code snippets inside the question string using ``` fences, ≤8 lines.
- concept_tag: 1–3 lowercase words naming the sub-skill tested (used to flag weak areas).
- Options ≤60 chars (they render as Telegram buttons).

Return ONLY JSON matching this schema (no prose, no code fences around the JSON):
{{ schema_json }}
