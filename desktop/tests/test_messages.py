import json

from aebuzz_desktop.messages import (
    Alert,
    Channel,
    display_name,
    format_alert,
    should_forward,
)

ME = "aa" * 32
SAM = "bb" * 32
DM = Channel("dm-1", "", "dm")
BACKEND = Channel("ch-1", "backend", "stream")
FORUM = Channel("ch-2", "announcements", "forum")
ATTENDANCE = Channel("ch-3", "Attendance", "stream")


def ev(kind=9, content="hello", pubkey=SAM, channel="ch-1", tags=()):
    return {"kind": kind, "content": content, "pubkey": pubkey, "tags": [["h", channel], *tags]}


# ── should_forward ──


def test_channel_message_forwarded():
    assert should_forward(ev(), ME, BACKEND, set())


def test_own_messages_skipped():
    assert not should_forward(ev(pubkey=ME), ME, BACKEND, set())


def test_reactions_edits_deletions_skipped():
    for kind in (7, 5, 9005, 40003, 40099):
        assert not should_forward(ev(kind=kind), ME, BACKEND, set())


def test_rich_messages_and_forum_kinds_forwarded():
    for kind in (40002, 45001, 45003):
        assert should_forward(ev(kind=kind), ME, BACKEND, set())


def test_muted_channel_skipped():
    assert not should_forward(ev(channel="ch-3"), ME, ATTENDANCE, {"ch-3"})


def test_mention_in_muted_channel_still_forwarded():
    assert should_forward(ev(channel="ch-3", tags=[["p", ME]]), ME, ATTENDANCE, {"ch-3"})


def test_broadcast_in_muted_channel_still_forwarded():
    assert should_forward(ev(channel="ch-3", tags=[["broadcast", "1"]]), ME, ATTENDANCE, {"ch-3"})


def test_workflow_owner_tag_is_not_a_mention():
    tags = [["buzz:workflow", "true"], ["p", ME, "", "owner"]]
    assert not should_forward(ev(channel="ch-3", tags=tags), ME, ATTENDANCE, {"ch-3"})


def test_huddle_started_only_in_dms():
    assert should_forward(ev(kind=48100, channel="dm-1"), ME, DM, set())
    assert not should_forward(ev(kind=48100), ME, BACKEND, set())


# ── format_alert (wording approved to match Buzz) ──


def test_dm_titled_by_sender():
    assert format_alert(ev(channel="dm-1", content="Hi there"), ME, DM, "Dana Lee") == Alert(
        "Dana Lee", "Hi there"
    )


def test_dm_huddle():
    assert format_alert(ev(kind=48100, channel="dm-1", content=""), ME, DM, "Dana Lee") == Alert(
        "Dana Lee", "Started a huddle"
    )


def test_dm_without_sender_name():
    assert format_alert(ev(channel="dm-1"), ME, DM, None).title == "Direct message"


def test_channel_message():
    assert format_alert(ev(content="deploy failed"), ME, BACKEND, "Sam") == Alert(
        "Sam in #backend", "deploy failed"
    )


def test_thread_reply():
    tags = [["e", "r" * 64, "", "reply"]]
    assert format_alert(ev(tags=tags), ME, BACKEND, "Sam").title == "Sam replied in #backend"


def test_broadcast_reply_reads_as_channel_message():
    tags = [["e", "r" * 64, "", "reply"], ["broadcast", "1"]]
    assert format_alert(ev(tags=tags), ME, BACKEND, "Sam").title == "Sam in #backend"


def test_mention():
    assert format_alert(ev(tags=[["p", ME]]), ME, BACKEND, "Sam").title == (
        "Sam mentioned you in #backend"
    )


def test_forum_post_and_comment():
    assert format_alert(ev(kind=45001, channel="ch-2"), ME, FORUM, "Sam").title == (
        "Sam posted in #announcements"
    )
    assert format_alert(ev(kind=45003, channel="ch-2"), ME, FORUM, "Sam").title == (
        "Sam commented in #announcements"
    )


def test_unknown_sender_falls_back():
    assert format_alert(ev(), ME, BACKEND, None).title == "New message in #backend"


# ── display_name ──


def test_display_name_order():
    def profile(**meta):
        return {"content": json.dumps(meta)}

    assert display_name(profile(display_name="Sam S", name="sam")) == "Sam S"
    assert display_name(profile(display_name=" ", name="sam")) == "sam"
    assert display_name(profile(nip05="s@x.com")) == "s@x.com"
    assert display_name(profile()) is None
    assert display_name({"content": "not json"}) is None
    assert display_name(None) is None
