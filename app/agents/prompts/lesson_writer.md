Write ONE complete lesson on the topic "{{ topic_title }}" (slug: {{ topic_slug }}),
part of the phase "{{ phase_title }}" in the student's AI-engineering roadmap.

Variant: {{ variant }}
- standard: normal pace for a beginner who is keeping up.
- simplified: the student scored below 50% last time — smaller steps, more analogies,
  gentler pace, re-explain prerequisites inline.
- advanced: the student is cruising — add depth, edge cases, and one harder challenge.
{% if recap %}
Open the concept section with a 3-line recap of "{{ recap }}" — the student struggled with it.
{% endif %}

The lesson must take 10–20 minutes total and follow this structure in the sections array,
in this exact order:
1. kind="concept" — the core explanation (objective is a separate top-level field).
2. kind="checkpoint" — one active-recall question on the concept just explained.
3. kind="example" — a real-world example tied to the student's life.
4. kind="diagram" — DESCRIBE a simple diagram in words (what boxes, what arrows); the
   student will sketch it in a notebook.
5. kind="code" — one runnable example (≤25 lines) with expected output shown in body_md
   inside a second code fence.
6. kind="checkpoint" — one question that requires predicting or modifying the code.

Checkpoint rules: options arrays have 3–4 short entries; correct_index is 0-based; hint
nudges WITHOUT revealing the answer; explanation teaches in 2–3 sentences why the correct
option is right.

The top-level summary field has 3–5 single-sentence bullets. The homework field is one
small task doable in under 15 minutes without a computer if needed.

Return ONLY JSON matching this schema (no prose, no code fences around the JSON):
{{ schema_json }}
