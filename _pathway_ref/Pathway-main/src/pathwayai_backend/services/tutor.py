from pathwayai_backend.config import Settings
from pathwayai_backend.llm.gateway import ModelGateway, ModelResult
from pathwayai_backend.prompts.mentor import (
    MENTOR_SYSTEM_PROMPT,
    TUTOR_QUESTION_PROMPT,
)


class TutorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.models = ModelGateway(settings)

    async def generate_message(
        self,
        topic: str,
        objective: str | None = None,
        memory: str = "No relevant memory retrieved.",
    ) -> ModelResult:
        question = (
            f"Topic: {topic}\n"
            f"Objective: {objective or self.settings.tutor_default_goal}"
        )
        fallback = (
            f"Focus on {topic}. Build one small implementation, explain the core "
            "tradeoff without notes, then test yourself with a realistic failure case."
        )
        return await self.models.generate(
            system_prompt=MENTOR_SYSTEM_PROMPT,
            user_prompt=TUTOR_QUESTION_PROMPT.format(
                question=question, memory=memory
            ),
            fallback=fallback,
        )
