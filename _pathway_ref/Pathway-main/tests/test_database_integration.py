import os
from uuid import uuid4

import pytest

from pathwayai_backend.config import Settings
from pathwayai_backend.db.repositories import Repository
from pathwayai_backend.db.session import Database


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_round_trip_against_isolated_postgres() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    database = Database(Settings(DATABASE_URL=database_url))
    try:
        async for session in database.session():
            repository = Repository(session)
            chat_id = f"test-{uuid4()}"
            user = await repository.get_or_create_user(
                telegram_chat_id=chat_id,
                display_name="Test User",
                target_role="Backend Engineer",
                timezone="UTC",
            )
            await repository.add_learning_log(user.id, "Studied transaction isolation")
            logs = await repository.recent_logs(user.id)
            assert logs[0].content == "Studied transaction isolation"
            await session.rollback()
            break
    finally:
        await database.close()
