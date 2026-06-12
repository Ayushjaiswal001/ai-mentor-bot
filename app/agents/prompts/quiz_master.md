Create a 5-question multiple-choice quiz on the topic "{{ topic_title }}"
(slug: {{ topic_slug }}), phase "{{ phase_title }}", difficulty: {{ difficulty }}.

Rules:
- Exactly 5 questions, each with exactly 4 options, correct_index 0-based.
- Mix: 2 conceptual, 2 code-reading ("what does this print?"), 1 spot-the-bug or
  fill-the-blank. Code snippets go inside the question string using ``` fences, ≤8 lines.
- Distractors must be plausible mistakes a beginner actually makes — never silly options.
- explanation: 1–3 sentences teaching why the correct answer is right (and why the
  tempting wrong one is wrong).
- concept_tag: a 1–3 word lowercase tag naming the sub-concept tested (used to track
  weak areas), e.g. "list slicing", "dict keys", "mutable default".
- Options must be short (≤60 chars) — they render as Telegram buttons text.

Return ONLY JSON matching this schema (no prose, no code fences around the JSON):
{{ schema_json }}
