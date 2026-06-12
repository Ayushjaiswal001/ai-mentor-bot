"""User bootstrap: load-or-create the (User, UserState) pair for a Telegram user."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import User as TgUser

from app.db.models import Phase, Topic, User, UserState


async def ensure_user(
    session: AsyncSession, tg_user: TgUser
) -> tuple[User, UserState, bool]:
    user = await session.scalar(select(User).where(User.tg_user_id == tg_user.id))
    if user is not None:
        state = await session.get(UserState, user.id)
        return user, state, False

    user = User(tg_user_id=tg_user.id, first_name=tg_user.first_name)
    session.add(user)
    await session.flush()
    first_topic = await session.scalar(
        select(Topic)
        .join(Phase, Topic.phase_id == Phase.id)
        .order_by(Phase.sort_order, Topic.sort_order)
        .limit(1)
    )
    state = UserState(
        user_id=user.id,
        current_phase_id=first_topic.phase_id if first_topic else None,
        current_topic_id=first_topic.id if first_topic else None,
    )
    session.add(state)
    await session.commit()
    return user, state, True
