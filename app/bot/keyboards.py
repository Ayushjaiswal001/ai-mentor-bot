"""Inline keyboard builders. Callback data formats (≤64 bytes):

  ob:hour:{19|20|21|off}        onboarding reminder hour
  nav:cont:{lesson_id}          continue lesson delivery
  nav:learn                     start/resume lesson
  nav:quiz:{topic_id}           start quiz for topic
  nav:later                     dismiss
  ck:{lesson_id}:{sec_idx}:{i}  checkpoint answer
  q:{attempt_id}:{q_idx}:{i}    quiz answer
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def hour_kb() -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(f"{h}:00", callback_data=f"ob:hour:{h}") for h in (19, 20, 21)
    ]
    return InlineKeyboardMarkup(
        [row, [InlineKeyboardButton("🔕 No reminders", callback_data="ob:hour:off")]]
    )


def continue_kb(lesson_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("▶️ Continue", callback_data=f"nav:cont:{lesson_id}")]]
    )


def post_lesson_kb(topic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎯 Take the quiz", callback_data=f"nav:quiz:{topic_id}")],
            [InlineKeyboardButton("⏸ Later", callback_data="nav:later")],
        ]
    )


def options_kb(prefix: str, a: int, b: int, n_options: int) -> InlineKeyboardMarkup:
    """Numbered answer buttons. prefix 'ck' → ck:{a}:{b}:{i}; prefix 'q' → q:{a}:{b}:{i}."""
    row = [
        InlineKeyboardButton(str(i + 1), callback_data=f"{prefix}:{a}:{b}:{i}")
        for i in range(n_options)
    ]
    return InlineKeyboardMarkup([row])


def next_lesson_kb(label: str = "▶️ Next lesson") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="nav:learn")]])


def revise_kb(n: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🔁 Review now ({n})", callback_data="nav:revise")]]
    )


def project_start_kb(pp_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🚀 Start project", callback_data=f"pj:start:{pp_id}")]]
    )


def project_step_kb(pp_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Step done", callback_data=f"pj:next:{pp_id}"),
                InlineKeyboardButton("💡 Guidance", callback_data=f"pj:guide:{pp_id}"),
            ]
        ]
    )


def project_submit_kb(pp_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎓 Submit project", callback_data=f"pj:submit:{pp_id}")]]
    )


def exercise_kb(ex_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💡 Hint", callback_data=f"ex:hint:{ex_id}"),
                InlineKeyboardButton("⏭ Skip", callback_data=f"ex:skip:{ex_id}"),
            ]
        ]
    )


def settings_kb() -> InlineKeyboardMarkup:
    diff_row = [
        InlineKeyboardButton("🐣 Simpler", callback_data="set:diff:simpler"),
        InlineKeyboardButton("⚖️ Normal", callback_data="set:diff:normal"),
        InlineKeyboardButton("🔥 Harder", callback_data="set:diff:harder"),
    ]
    hour_row = [
        InlineKeyboardButton(f"⏰ {h}:00", callback_data=f"set:hour:{h}") for h in (19, 20, 21)
    ]
    off_row = [InlineKeyboardButton("🔕 Reminder off", callback_data="set:hour:off")]
    return InlineKeyboardMarkup([diff_row, hour_row, off_row])


def today_kb(has_lesson: bool, due_count: int) -> InlineKeyboardMarkup | None:
    rows = []
    if has_lesson:
        rows.append([InlineKeyboardButton("📘 Today's lesson", callback_data="nav:learn")])
    if due_count > 0:
        rows.append(
            [InlineKeyboardButton(f"🔁 Reviews ({due_count})", callback_data="nav:revise")]
        )
    return InlineKeyboardMarkup(rows) if rows else None
