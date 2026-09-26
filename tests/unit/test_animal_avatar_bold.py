from unittest.mock import MagicMock, patch
import pytest

from ehforwarderbot import Message
from ehforwarderbot.chat import GroupChat, ChatMember, PrivateChat
from efb_telegram_master.slave_message import SlaveMessageProcessor
from efb_telegram_master.bot_manager import TelegramBotManager


def test_land_animal_emojis_list():
    expected = ["🐱", "🐶", "🦊", "🐼", "🐨", "🐯", "🦁", "🐰", "🐻", "🐵", "🐷", "🐸"]
    assert SlaveMessageProcessor.LAND_ANIMAL_EMOJIS == expected


def test_get_author_emoji_deterministic():
    author1 = MagicMock(spec=ChatMember)
    author1.uid = "user_wxid_1001"
    author1.name = "Alice"

    author2 = MagicMock(spec=ChatMember)
    author2.uid = "user_wxid_1002"
    author2.name = "Bob"

    emoji1 = SlaveMessageProcessor.get_author_emoji(author1)
    emoji2 = SlaveMessageProcessor.get_author_emoji(author2)

    assert emoji1 in SlaveMessageProcessor.LAND_ANIMAL_EMOJIS
    assert emoji2 in SlaveMessageProcessor.LAND_ANIMAL_EMOJIS
    # Deterministic check
    assert SlaveMessageProcessor.get_author_emoji(author1) == emoji1
    assert SlaveMessageProcessor.get_author_emoji(author2) == emoji2


def test_generate_message_template_group_singly_linked():
    processor = MagicMock(spec=SlaveMessageProcessor)
    processor.get_author_emoji = SlaveMessageProcessor.get_author_emoji
    processor.logger = MagicMock()

    group = MagicMock(spec=GroupChat)
    group.long_name = "TechGroup"

    member = MagicMock(spec=ChatMember)
    member.uid = "user_001"
    member.long_name = "Charlie"

    msg = Message()
    msg.uid = "msg_001"
    msg.chat = group
    msg.author = member

    template = SlaveMessageProcessor.generate_message_template(processor, msg, singly_linked=True)
    author_emoji = SlaveMessageProcessor.get_author_emoji(member)
    assert template == f"{author_emoji} Charlie:"


def test_generate_message_template_group_unlinked():
    processor = MagicMock(spec=SlaveMessageProcessor)
    processor.get_author_emoji = SlaveMessageProcessor.get_author_emoji
    processor.logger = MagicMock()

    group = MagicMock(spec=GroupChat)
    group.channel_emoji = "💬"
    group.long_name = "TechGroup"

    member = MagicMock(spec=ChatMember)
    member.uid = "user_001"
    member.long_name = "Charlie"

    msg = Message()
    msg.uid = "msg_001"
    msg.chat = group
    msg.author = member

    template = SlaveMessageProcessor.generate_message_template(processor, msg, singly_linked=False)
    author_emoji = SlaveMessageProcessor.get_author_emoji(member)
    assert author_emoji in template
    assert "Charlie" in template
    assert "TechGroup" in template
    assert template == f"💬👥 {author_emoji} Charlie [TechGroup]:"


def test_bot_manager_send_message_bold_prefix_html():
    bot_manager = MagicMock(spec=TelegramBotManager)
    bot_manager._bot_send_message_fallback = MagicMock(return_value="sent_msg")

    res = TelegramBotManager.send_message(
        bot_manager,
        12345,
        text="Hello world",
        prefix="🐱 Alice:",
        suffix="",
        parse_mode="HTML"
    )

    bot_manager._bot_send_message_fallback.assert_called_once()
    _, kwargs = bot_manager._bot_send_message_fallback.call_args
    assert kwargs['text'] == "<b>🐱 Alice:</b>\nHello world"


def test_bot_manager_send_message_escaped_html():
    bot_manager = MagicMock(spec=TelegramBotManager)
    bot_manager._bot_send_message_fallback = MagicMock(return_value="sent_msg")

    res = TelegramBotManager.send_message(
        bot_manager,
        12345,
        text="Hello world",
        prefix="🐱 Bob <Dev> & Charlie:",
        suffix="",
        parse_mode="HTML"
    )

    bot_manager._bot_send_message_fallback.assert_called_once()
    _, kwargs = bot_manager._bot_send_message_fallback.call_args
    assert kwargs['text'] == "<b>🐱 Bob &lt;Dev&gt; &amp; Charlie:</b>\nHello world"


def test_bot_manager_send_message_plain_without_html():
    bot_manager = MagicMock(spec=TelegramBotManager)
    bot_manager._bot_send_message_fallback = MagicMock(return_value="sent_msg")

    res = TelegramBotManager.send_message(
        bot_manager,
        12345,
        text="Hello world",
        prefix="Prefix",
        suffix="Suffix"
    )

    bot_manager._bot_send_message_fallback.assert_called_once()
    _, kwargs = bot_manager._bot_send_message_fallback.call_args
    assert kwargs['text'] == "Prefix\nHello world\nSuffix"


def test_bot_manager_edit_message_text_bold_prefix_html():
    bot_manager = MagicMock(spec=TelegramBotManager)
    bot_manager._bot_edit_message_text_fallback = MagicMock(return_value="edited_msg")

    res = TelegramBotManager.edit_message_text(
        bot_manager,
        chat_id=12345,
        message_id=6789,
        text="Edited content",
        prefix="🐶 David:",
        suffix="",
        parse_mode="HTML"
    )

    bot_manager._bot_edit_message_text_fallback.assert_called_once()
    _, kwargs = bot_manager._bot_edit_message_text_fallback.call_args
    assert kwargs['text'] == "<b>🐶 David:</b>\nEdited content"


def test_bot_manager_caption_affix_bold_prefix_html():
    bot_manager = MagicMock(spec=TelegramBotManager)
    mock_fn = MagicMock(return_value="sent_media")
    decorated_fn = TelegramBotManager.Decorators.caption_affix_decorator(mock_fn)

    res = decorated_fn(
        bot_manager,
        chat_id=12345,
        caption="Photo caption",
        prefix="🦊 Eve:",
        suffix="",
        parse_mode="HTML"
    )

    mock_fn.assert_called_once()
    args, kwargs = mock_fn.call_args
    assert kwargs['caption'] == "<b>🦊 Eve:</b>\nPhoto caption"


def test_bot_manager_empty_prefix_html():
    bot_manager = MagicMock(spec=TelegramBotManager)
    bot_manager._bot_send_message_fallback = MagicMock(return_value="sent_msg")

    res = TelegramBotManager.send_message(
        bot_manager,
        12345,
        text="No prefix content",
        prefix="",
        suffix="",
        parse_mode="HTML"
    )

    bot_manager._bot_send_message_fallback.assert_called_once()
    _, kwargs = bot_manager._bot_send_message_fallback.call_args
    assert kwargs['text'] == "No prefix content"

