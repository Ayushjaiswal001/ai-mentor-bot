Create ONE small coding exercise for the topic "{{ topic_title }}" (slug: {{ topic_slug }}),
phase "{{ phase_title }}", difficulty: {{ difficulty }}.

Rules:
- Solvable in 10–15 minutes by a beginner who just finished the lesson on this topic.
- prompt_md: a clear problem statement with one concrete example of expected input/output.
  Plain Markdown only (**bold**, `inline code`, ``` fences).
- starter_code: a tiny scaffold (function signature or a TODO comment), or "" if not useful.
- hints: 2–4 PROGRESSIVE hints — hint 1 is a gentle nudge, the last is almost the approach,
  but NONE reveal the full solution code.
- rubric: 2–5 concrete checks the grader will use (e.g. "handles empty input",
  "uses a dict not nested loops", "prints exactly the required format").

Return ONLY JSON matching this schema (no prose, no code fences around the JSON):
{{ schema_json }}
