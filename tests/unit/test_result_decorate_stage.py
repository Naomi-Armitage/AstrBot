from astrbot.core.message.components import Plain
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


class _DummyEvent(AstrMessageEvent):
    async def send(self, message):
        return None


def _make_event(platform_name: str, message_id: str | int) -> AstrMessageEvent:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot123"
    message.session_id = "session123"
    message.message_id = message_id
    message.sender = MessageMember(user_id="user123", nickname="TestUser")
    message.message = [Plain(text="hello")]
    message.message_str = "hello"
    message.raw_message = None
    return _DummyEvent(
        message_str="hello",
        message_obj=message,
        platform_meta=PlatformMetadata(
            name=platform_name,
            description=f"{platform_name} test",
            id=f"{platform_name}_id",
        ),
        session_id="session123",
    )


def test_should_attach_quote_reply_accepts_numeric_telegram_message_id() -> None:
    stage = ResultDecorateStage()
    event = _make_event("telegram", "123456")

    assert stage._should_attach_quote_reply(event) is True


def test_should_attach_quote_reply_rejects_uuid_telegram_message_id() -> None:
    stage = ResultDecorateStage()
    event = _make_event("telegram", "a30802eead8a4820930db6b8abd70290")

    assert stage._should_attach_quote_reply(event) is False


def test_should_attach_quote_reply_keeps_non_telegram_behavior() -> None:
    stage = ResultDecorateStage()
    event = _make_event("webchat", "a30802eead8a4820930db6b8abd70290")

    assert stage._should_attach_quote_reply(event) is True
