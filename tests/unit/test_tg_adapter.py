import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.constants import ChatType
from telegram.error import BadRequest

import astrbot.api.message_components as Comp
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter


def _build_update_with_video(video) -> SimpleNamespace:
    message = SimpleNamespace(
        chat=SimpleNamespace(id=12345, type=ChatType.PRIVATE),
        message_id=1001,
        from_user=SimpleNamespace(id=42, username="tester"),
        reply_to_message=None,
        is_topic_message=False,
        message_thread_id=None,
        media_group_id=None,
        text=None,
        entities=None,
        voice=None,
        photo=None,
        sticker=None,
        document=None,
        video=video,
        caption=None,
        caption_entities=None,
    )
    return SimpleNamespace(message=message)


def _build_text_message(
    text: str,
    *,
    chat_type: str = "group",
    from_user_id: int = 42,
    from_username: str = "tester",
    reply_to_message=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        chat=SimpleNamespace(id=12345, type=chat_type),
        message_id=1001,
        from_user=SimpleNamespace(id=from_user_id, username=from_username),
        reply_to_message=reply_to_message,
        is_topic_message=False,
        message_thread_id=None,
        media_group_id=None,
        text=text,
        entities=None,
        voice=None,
        photo=None,
        sticker=None,
        document=None,
        video=None,
        caption=None,
        caption_entities=None,
    )


def _build_update_with_text(text: str, reply_to_message=None) -> SimpleNamespace:
    return SimpleNamespace(
        message=_build_text_message(text=text, reply_to_message=reply_to_message),
    )


def _build_context() -> SimpleNamespace:
    return SimpleNamespace(bot=SimpleNamespace(username="bot", id=1))


@pytest.mark.asyncio
async def test_convert_message_video_too_big_falls_back_to_plain_placeholder():
    adapter = TelegramPlatformAdapter(
        platform_config={"telegram_token": "123456:ABCDEF", "id": "telegram"},
        platform_settings={},
        event_queue=asyncio.Queue(),
    )

    video = SimpleNamespace(
        get_file=AsyncMock(side_effect=BadRequest("File is too big")),
        file_name="large_video.mp4",
    )
    update = _build_update_with_video(video)
    context = _build_context()

    abm = await adapter.convert_message(update, context)

    assert abm is not None
    assert abm.message_str == "[Video: large_video.mp4 (File is too big)]"
    assert len(abm.message) == 1
    assert isinstance(abm.message[0], Comp.Plain)
    assert "File is too big" in abm.message[0].text


@pytest.mark.asyncio
async def test_convert_message_video_non_size_bad_request_is_raised():
    adapter = TelegramPlatformAdapter(
        platform_config={"telegram_token": "123456:ABCDEF", "id": "telegram"},
        platform_settings={},
        event_queue=asyncio.Queue(),
    )

    video = SimpleNamespace(
        get_file=AsyncMock(side_effect=BadRequest("wrong file identifier")),
        file_name="bad_video.mp4",
    )
    update = _build_update_with_video(video)
    context = _build_context()

    with pytest.raises(BadRequest):
        await adapter.convert_message(update, context)


@pytest.mark.asyncio
async def test_convert_message_group_reply_command_keeps_original_slash_command():
    adapter = TelegramPlatformAdapter(
        platform_config={"telegram_token": "123456:ABCDEF", "id": "telegram"},
        platform_settings={},
        event_queue=asyncio.Queue(),
    )

    reply_message = _build_text_message(
        text="Previous bot response",
        from_user_id=1,
        from_username="bot",
        reply_to_message=None,
    )
    update = _build_update_with_text(
        text="/grok生图 一只可爱的猫咪",
        reply_to_message=reply_message,
    )
    context = _build_context()

    abm = await adapter.convert_message(update, context)

    assert abm is not None
    assert abm.message_str == "/grok生图 一只可爱的猫咪"
    assert any(
        isinstance(seg, Comp.Plain) and seg.text == "/grok生图 一只可爱的猫咪"
        for seg in abm.message
    )
