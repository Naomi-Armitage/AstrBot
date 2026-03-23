from pathlib import Path

import pytest
from PIL import Image as PILImage

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
from tests.fixtures.mocks import MockTelegramBuilder


def _create_webp_file(path: Path) -> Path:
    PILImage.new("RGBA", (64, 64), color=(255, 0, 0, 0)).save(path, format="WEBP")
    return path


def _create_message() -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot123"
    message.session_id = "session123"
    message.message_id = "msg123"
    message.sender = MessageMember(user_id="user123", nickname="Tester")
    message.message = []
    message.message_str = ""
    return message


def _create_platform_meta() -> PlatformMetadata:
    return PlatformMetadata(
        name="telegram",
        description="Telegram",
        id="telegram",
    )


@pytest.mark.asyncio
async def test_send_with_client_prefers_sticker_for_webp(tmp_path: Path):
    bot = MockTelegramBuilder.create_bot()
    fake_webp = _create_webp_file(tmp_path / "sticker.jpg")

    await TelegramPlatformEvent.send_with_client(
        bot,
        MessageChain(chain=[Image.fromFileSystem(str(fake_webp))]),
        "user123",
    )

    bot.send_sticker.assert_awaited_once()
    assert bot.send_sticker.await_args.kwargs["sticker"] == str(fake_webp)
    bot.send_document.assert_not_awaited()
    bot.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_image_with_fallback_uses_document_when_sticker_fails(tmp_path: Path):
    bot = MockTelegramBuilder.create_bot()
    bot.send_sticker.side_effect = RuntimeError("sticker failed")
    fake_webp = _create_webp_file(tmp_path / "downloaded.jpg")

    await TelegramPlatformEvent._send_image_with_fallback(
        bot,
        str(fake_webp),
        {"chat_id": "user123"},
        user_name="user123",
        use_media_action=True,
    )

    bot.send_sticker.assert_awaited_once()
    bot.send_document.assert_awaited_once()
    assert bot.send_document.await_args.kwargs["document"] == str(fake_webp)
    assert bot.send_document.await_args.kwargs["filename"].endswith(".webp")
    bot.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chain_items_uses_same_webp_strategy(tmp_path: Path):
    bot = MockTelegramBuilder.create_bot()
    fake_webp = _create_webp_file(tmp_path / "streaming.jpg")
    event = TelegramPlatformEvent(
        message_str="",
        message_obj=_create_message(),
        platform_meta=_create_platform_meta(),
        session_id="session123",
        client=bot,
    )

    await event._process_chain_items(
        MessageChain(chain=[Image.fromFileSystem(str(fake_webp))]),
        {"chat_id": "user123"},
        "user123",
        None,
        lambda _: None,
    )

    bot.send_sticker.assert_awaited_once()
