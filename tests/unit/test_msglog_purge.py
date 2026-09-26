import datetime
import os
import tempfile

import pytest

from efb_telegram_master.db import DatabaseManager, MsgLog, database


@pytest.fixture(scope="function")
def mem_db():
    # Mirror DatabaseManager.__init__: init -> start -> connect.
    # NOTE: a temp file (not ":memory:") is required: SqliteQueueDatabase
    # serves SELECTs on the calling thread's connection while writes go
    # through the writer thread -- with ":memory:" those are two different
    # empty databases.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.init(path)
    database.start()
    database.connect()
    database.create_tables([MsgLog])
    yield database
    database.drop_tables([MsgLog])
    database.stop()
    database.close()
    os.unlink(path)


def _make_row(days_old, slave_message_id="slave_mid", text="hello", pickle_data=None,
              file_id=None, file_unique_id=None, mime=None, media_type=None,
              master_msg_id=None):
    now = datetime.datetime.now()
    mid = master_msg_id or "tg_%s_%s" % (days_old, slave_message_id)
    return MsgLog.create(
        master_msg_id=mid,
        slave_message_id=slave_message_id,
        slave_origin_uid="slave_channel$slave_chat",
        slave_member_uid="slave_channel$slave_member",
        msg_type="Text",
        text=text,
        sent_to="slave_channel$slave_chat",
        pickle=pickle_data,
        time=now - datetime.timedelta(days=days_old),
        file_id=file_id,
        file_unique_id=file_unique_id,
        mime=mime,
        media_type=media_type,
    )


def test_strip_old_keeps_mapping(mem_db):
    _make_row(60, master_msg_id="old_msg", text="secret text",
              pickle_data=b"pickled", file_id="fid", mime="image/jpeg",
              media_type="photo")
    _make_row(5, master_msg_id="new_msg", text="fresh text")

    stats = DatabaseManager.purge_old_messages(strip_after_days=30,
                                               purge_after_days=180,
                                               vacuum=False)

    assert stats["stripped"] == 1
    assert stats["deleted"] == 0

    old = MsgLog.get(MsgLog.master_msg_id == "old_msg")
    # Content is wiped...
    assert old.text == ""
    assert old.pickle is None
    assert old.file_id is None
    assert old.mime is None
    assert old.media_type is None
    # ...but the ID mapping survives.
    assert old.slave_message_id == "slave_mid"
    assert old.slave_origin_uid == "slave_channel$slave_chat"
    assert old.master_msg_id == "old_msg"

    new = MsgLog.get(MsgLog.master_msg_id == "new_msg")
    assert new.text == "fresh text"


def test_purge_very_old_rows(mem_db):
    _make_row(200, master_msg_id="ancient_msg", text="ancient")
    _make_row(60, master_msg_id="old_msg", text="old")

    stats = DatabaseManager.purge_old_messages(strip_after_days=30,
                                               purge_after_days=180,
                                               vacuum=False)

    assert stats["stripped"] == 1  # only the 60-day row (the 200-day one is purged)
    assert stats["deleted"] == 1
    assert MsgLog.select().where(MsgLog.master_msg_id == "ancient_msg").count() == 0
    assert MsgLog.select().where(MsgLog.master_msg_id == "old_msg").count() == 1


def test_chat_head_rows_are_never_purged(mem_db):
    _make_row(500, master_msg_id="chat_head_msg",
              slave_message_id=DatabaseManager.CHAT_HEAD_SLAVE_MSG_ID,
              text="Reply to this message to chat with Foo.")

    stats = DatabaseManager.purge_old_messages(strip_after_days=30,
                                               purge_after_days=180,
                                               vacuum=False)

    assert stats["stripped"] == 0
    assert stats["deleted"] == 0
    row = MsgLog.get(MsgLog.master_msg_id == "chat_head_msg")
    assert row.text == "Reply to this message to chat with Foo."


def test_purge_is_batched(mem_db):
    for i in range(5):
        _make_row(200, master_msg_id="ancient_%d" % i)

    stats = DatabaseManager.purge_old_messages(strip_after_days=0,
                                               purge_after_days=180,
                                               batch_size=2,
                                               vacuum=False)

    assert stats["deleted"] == 5
    assert MsgLog.select().count() == 0


def test_disabled_tiers_are_noop(mem_db):
    _make_row(500, master_msg_id="ancient_msg", text="ancient")

    stats = DatabaseManager.purge_old_messages(strip_after_days=0,
                                               purge_after_days=0,
                                               vacuum=False)

    assert stats == {"stripped": 0, "deleted": 0}
    assert MsgLog.select().count() == 1


def test_invalid_arguments(mem_db):
    with pytest.raises(ValueError):
        DatabaseManager.purge_old_messages(strip_after_days=-1)
    with pytest.raises(ValueError):
        DatabaseManager.purge_old_messages(purge_after_days=-1)
    with pytest.raises(ValueError):
        DatabaseManager.purge_old_messages(strip_after_days=90, purge_after_days=30)
    with pytest.raises(ValueError):
        DatabaseManager.purge_old_messages(batch_size=0)


def test_estimate_purge_is_dry_run(mem_db):
    _make_row(200, master_msg_id="ancient_msg", text="ancient")
    _make_row(60, master_msg_id="old_msg", text="old")
    _make_row(500, master_msg_id="chat_head_msg",
              slave_message_id=DatabaseManager.CHAT_HEAD_SLAVE_MSG_ID,
              text="Reply to this message to chat with Foo.")
    _make_row(5, master_msg_id="new_msg", text="fresh")

    estimate = DatabaseManager.estimate_purge(strip_after_days=30, purge_after_days=180)

    assert estimate == {"strip": 1, "purge": 1}
    # Nothing was modified.
    assert MsgLog.select().count() == 4
    assert MsgLog.get(MsgLog.master_msg_id == "old_msg").text == "old"
    assert MsgLog.get(MsgLog.master_msg_id == "ancient_msg").text == "ancient"


def test_estimate_purge_matches_actual_purge(mem_db):
    _make_row(200, master_msg_id="ancient_msg", text="ancient")
    _make_row(60, master_msg_id="old_msg", text="old")
    _make_row(5, master_msg_id="new_msg", text="fresh")

    estimate = DatabaseManager.estimate_purge(strip_after_days=30, purge_after_days=180)
    stats = DatabaseManager.purge_old_messages(strip_after_days=30,
                                               purge_after_days=180,
                                               vacuum=False)

    assert estimate["strip"] == stats["stripped"]
    assert estimate["purge"] == stats["deleted"]


def test_seconds_until_next_purge():
    from datetime import datetime
    from efb_telegram_master import TelegramChannel

    now = datetime.now()
    # Target later today: delay is positive and less than a day.
    future_hour = (now.hour + 2) % 24
    delay = TelegramChannel._seconds_until_next_purge(future_hour)
    assert 0 < delay <= 24 * 3600
    # Target already passed today: delay points to tomorrow.
    past_hour = (now.hour - 2) % 24
    delay = TelegramChannel._seconds_until_next_purge(past_hour)
    assert 0 < delay <= 24 * 3600
    # Target is exactly this hour (minute 0 already passed or not):
    # delay is within (0, 24h].
    delay = TelegramChannel._seconds_until_next_purge(now.hour)
    assert 0 < delay <= 24 * 3600
