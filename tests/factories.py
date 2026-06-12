"""Canned schema objects standing in for LLM output (FakeLLM)."""

from app.agents.schemas import MCQ, Checkpoint, LessonSchema, LessonSection, QuizSchema


def fake_lesson(topic_slug: str = "variables") -> LessonSchema:
    cp = Checkpoint(
        question="What does `x = 5` do?",
        options=["Compares x to 5", "Stores 5 in x", "Prints 5"],
        correct_index=1,
        hint="Think about the = sign.",
        explanation="A single = assigns the value on the right to the name on the left.",
    )
    return LessonSchema(
        topic_slug=topic_slug,
        title="Variables",
        objective="Understand what variables are and how assignment works.",
        sections=[
            LessonSection(kind="concept", title="The idea", body_md="A variable is a **box**."),
            LessonSection(kind="checkpoint", title="Quick check", checkpoint=cp),
            LessonSection(kind="example", title="Real life", body_md="Your marks in `marks`."),
            LessonSection(kind="diagram", title="Sketch it", body_md="A box with an arrow."),
            LessonSection(
                kind="code", title="Try it", body_md="```python\nx = 5\nprint(x)\n```"
            ),
            LessonSection(kind="checkpoint", title="Code check", checkpoint=cp),
        ],
        summary=["Variables store values.", "= assigns.", "Names point to data."],
        homework="Create three variables about your day and print them.",
    )


def fake_quiz(topic_slug: str = "variables", correct_index: int = 0) -> QuizSchema:
    return QuizSchema(
        topic_slug=topic_slug,
        questions=[
            MCQ(
                question=f"Question {i}?",
                options=["alpha", "beta", "gamma", "delta"],
                correct_index=correct_index,
                explanation="Because reasons.",
                concept_tag=f"tag-{i}",
            )
            for i in range(5)
        ],
    )
