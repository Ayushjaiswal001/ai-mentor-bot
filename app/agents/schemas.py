"""Pydantic output contracts for all LLM agents. The router validates against these."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Checkpoint(BaseModel):
    question: str
    options: list[str] = Field(min_length=3, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    hint: str
    explanation: str


class LessonSection(BaseModel):
    kind: Literal["concept", "example", "diagram", "code", "checkpoint"]
    title: str
    body_md: str = ""
    checkpoint: Checkpoint | None = None

    @model_validator(mode="after")
    def checkpoint_present_iff_kind(self) -> "LessonSection":
        if self.kind == "checkpoint" and self.checkpoint is None:
            raise ValueError("checkpoint section requires a checkpoint object")
        return self


class LessonSchema(BaseModel):
    topic_slug: str
    title: str
    objective: str
    sections: list[LessonSection] = Field(min_length=5, max_length=10)
    summary: list[str] = Field(min_length=3, max_length=6)
    homework: str

    @model_validator(mode="after")
    def has_active_recall(self) -> "LessonSchema":
        kinds = [s.kind for s in self.sections]
        if kinds.count("checkpoint") < 1:
            raise ValueError("lesson must contain at least one checkpoint section")
        if "code" not in kinds:
            raise ValueError("lesson must contain a code section")
        return self


class MCQ(BaseModel):
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str
    concept_tag: str


class QuizSchema(BaseModel):
    topic_slug: str
    questions: list[MCQ] = Field(min_length=5, max_length=5)


class ExerciseSchema(BaseModel):
    topic_slug: str
    title: str
    prompt_md: str
    starter_code: str = ""
    hints: list[str] = Field(min_length=2, max_length=4)  # progressive Socratic hints
    rubric: list[str] = Field(min_length=2, max_length=5)  # criteria the evaluator checks


class EvalSchema(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(max_length=5)
    issues: list[str] = Field(max_length=5)
    suggestion: str  # one concrete, encouraging next step (Socratic, not the full solution)


class ProjectStep(BaseModel):
    title: str
    goal: str
    details_md: str
    done_when: str  # how the student knows this step is complete


class ProjectPlan(BaseModel):
    project_slug: str
    title: str
    overview: str
    steps: list[ProjectStep] = Field(min_length=4, max_length=10)


class AssessmentSchema(BaseModel):
    questions: list[MCQ] = Field(min_length=6, max_length=8)
