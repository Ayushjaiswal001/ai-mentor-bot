Break the project "{{ project_title }}" into a step-by-step plan {{ name }} can build over
several days. Context: this is the capstone-style project for the phase "{{ phase_title }}"
in a beginner→advanced AI-engineering roadmap. Difficulty: {{ difficulty }}.

{% if brief %}Project brief: {{ brief }}{% endif %}

Rules:
- 4–10 steps, each a self-contained chunk of ~30–60 minutes of work.
- Steps build on each other from setup → core feature → polish.
- For each step: a short title, a one-line goal, details_md (what to do + a concrete tip,
  plain Markdown only), and done_when (a checkable definition of done).
- overview: 2–3 sentences on what they'll build and what they'll learn.
- Assume the student knows the phase's topics but is new to building this kind of project.

Return ONLY JSON matching this schema (no prose, no code fences around the JSON):
{{ schema_json }}
