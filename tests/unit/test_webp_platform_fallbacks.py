import base64
from pathlib import Path

import pytest
from PIL import Image as PILImage

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _create_webp_file(path: Path) -> Path:
    PILImage.new("RGBA", (64, 64), color=(255, 0, 0, 0)).save(path, format="WEBP")
    return path


@pytest.mark.asyncio
async def test_aiocqhttp_converts_webp_to_png_payload(tmp_path: Path):
    fake_webp = _create_webp_file(tmp_path / "sticker.jpg")

    payload = await AiocqhttpMessageEvent._from_segment_to_dict(
        Image.fromFileSystem(str(fake_webp))
    )

    image_bytes = base64.b64decode(payload["data"]["file"].removeprefix("base64://"))
    assert image_bytes.startswith(PNG_HEADER)


@pytest.mark.asyncio
async def test_qqofficial_converts_webp_to_png_payload(tmp_path: Path):
    fake_webp = _create_webp_file(tmp_path / "sticker.jpg")

    _, image_base64, image_path, *_ = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain(chain=[Image.fromFileSystem(str(fake_webp))])
    )

    assert image_path is not None
    assert image_path.endswith(".png")
    image_bytes = base64.b64decode(image_base64)
    assert image_bytes.startswith(PNG_HEADER)
