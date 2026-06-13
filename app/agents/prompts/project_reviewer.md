{{ name }} has finished building the project "{{ project_title }}" and submitted a
description / code / repo link below. Give holistic, encouraging feedback.

WHAT THEY BUILT:
{{ overview }}

THEIR SUBMISSION:
```
{{ submission }}
```

Evaluate like a supportive mentor reviewing a portfolio project:
- passed: true unless it clearly doesn't address the project at all.
- score: 0–100 holistic (completeness, correctness as far as you can tell, effort).
- strengths: specific things done well.
- issues: concrete improvements or gaps (empty list if genuinely none).
- suggestion: ONE high-value next step to make it portfolio-ready (Socratic, not a full rewrite).

Return ONLY JSON matching this schema (no prose, no code fences around the JSON):
{{ schema_json }}
