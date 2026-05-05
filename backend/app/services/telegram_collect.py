"""
Збір коментарів під постами Telegram-каналу через MTProto (Telethon).

Потрібні змінні середовища (отримати api_id/api_hash на https://my.telegram.org,
рядок сесії — одноразово через локальний скрипт з StringSession):

  TELEGRAM_API_ID
  TELEGRAM_API_HASH
  TELEGRAM_SESSION_STRING

Канал має мати увімкнені «Коментарі» (прив’язана група обговорення).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetDiscussionMessageRequest

from app.analytics.mock_metadata import enrich_with_mock_metadata
from app.config import get_settings

logger = logging.getLogger(__name__)

_CHANNEL_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/([^/?#]+)",
    re.I,
)


def parse_channel_username(target: str) -> str:
    raw = (target or "").strip()
    if not raw:
        raise ValueError("Порожнє посилання або юзернейм каналу")
    m = _CHANNEL_RE.search(raw)
    if m:
        return m.group(1).lstrip("@")
    return raw.lstrip("@").strip()


async def collect_channel_comments(
    *,
    channel_hint: str,
    post_limit: int,
) -> list[dict[str, Any]]:
    """Повертає список коментарів як items для raw_data."""
    settings = get_settings()
    sid = settings.telegram_api_id
    shash = settings.telegram_api_hash
    sess = settings.telegram_session_string

    if not sid or not shash or not sess:
        reason = (
            "Не налаштовано TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING. "
            "Додайте їх у .env або docker-compose (див. коментар у telegram_collect.py)."
        )
        logger.warning(reason)
        return [
            {
                "user_id": "_credentials",
                "text": reason,
                "metadata": {"mock": True, "error": "telegram_env_missing"},
            }
        ]

    username = parse_channel_username(channel_hint)
    client = TelegramClient(
        StringSession(sess),
        int(sid),
        str(shash),
    )

    items: list[dict[str, Any]] = []
    max_per_post = 300

    await client.connect()
    try:
        if not await client.is_user_authorized():
            return [
                {
                    "user_id": "_session",
                    "text": "Telegram-сесія недійсна. Перегенеруйте TELEGRAM_SESSION_STRING.",
                    "metadata": {"mock": True, "error": "telegram_session_invalid"},
                }
            ]

        channel = await client.get_entity(username)
        full = await client(GetFullChannelRequest(channel=channel))
        linked_id = getattr(full.full_chat, "linked_chat_id", None)
        if not linked_id:
            return [
                {
                    "user_id": "_channel",
                    "text": (
                        "У цього каналу немає прив’язаної групи обговорення "
                        "(коментарі вимкнені або канал приватний без доступу)."
                    ),
                    "metadata": {
                        "mock": True,
                        "error": "no_discussion_chat",
                        "channel": username,
                    },
                }
            ]

        discussion_chat = await client.get_entity(linked_id)

        async for post in client.iter_messages(channel, limit=post_limit):
            if not post or getattr(post, "action", None):
                continue
            try:
                disc = await client(
                    GetDiscussionMessageRequest(
                        peer=channel,
                        msg_id=post.id,
                    )
                )
            except RPCError as e:
                logger.info("No discussion for post %s: %s", post.id, e)
                continue

            if not disc.messages:
                continue
            top_disc = disc.messages[0]
            discussion_peer = disc.chats[0] if disc.chats else discussion_chat

            n = 0
            async for comment in client.iter_messages(
                discussion_peer,
                reply_to=top_disc.id,
            ):
                if not comment:
                    continue
                if comment.id == top_disc.id:
                    continue
                text = (getattr(comment, "message", None) or "").strip()
                if not text:
                    continue
                sender = await comment.get_sender()
                tg_uid = (
                    getattr(sender, "id", None)
                    if sender
                    else getattr(comment, "sender_id", None)
                )
                tg_uname = getattr(sender, "username", None) if sender else None
                tg_tag = f"@{tg_uname}" if tg_uname else None
                fn = getattr(sender, "first_name", None) if sender else None
                ln = getattr(sender, "last_name", None) if sender else None
                display_name = (
                    f"{fn or ''} {ln or ''}".strip() if (fn or ln) else None
                )
                # Для корпусу / пошуку: пріоритет публічного тегу
                user_label = tg_tag if tg_tag else (f"id:{tg_uid}" if tg_uid else "unknown")

                base_meta: dict[str, Any] = {
                    "mock": False,
                    "source": "telegram_mtproto",
                    "telegram_tag": tg_tag,
                    "telegram_username": tg_uname,
                    "telegram_user_id": tg_uid,
                    "telegram_display_name": display_name,
                    "channel_post_id": post.id,
                    "discussion_msg_id": top_disc.id,
                    "comment_id": comment.id,
                    "date": comment.date.isoformat()
                    if getattr(comment, "date", None)
                    else None,
                }
                row_post = {
                    "user_id": user_label,
                    "text": text[:8000],
                    "metadata": base_meta,
                }
                row_post["metadata"] = enrich_with_mock_metadata(row_post)

                items.append(
                    {
                        "user_id": user_label,
                        "text": text[:8000],
                        "metadata": row_post["metadata"],
                    }
                )
                n += 1
                if n >= max_per_post:
                    break

        if not items:
            return [
                {
                    "user_id": "_empty",
                    "text": (
                        "Коментарів не знайдено за останні пости "
                        f"(перевірено постів: {post_limit}). Можливо, немає коментарів або немає доступу."
                    ),
                    "metadata": {
                        "mock": True,
                        "error": "no_comments",
                        "channel": username,
                        "posts_checked": post_limit,
                    },
                }
            ]

        return items
    finally:
        await client.disconnect()
