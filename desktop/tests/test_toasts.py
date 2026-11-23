from aebuzz_desktop.toasts import CrossAppDuplicateFilter, NewToastTracker, Toast, parse_toast


def test_parse_skips_whitespace_filler():
    assert parse_toast(["Sooraj in #backend", "\n\t\t\t", "the message body"]) == Toast(
        "Sooraj in #backend", "the message body"
    )


def test_parse_title_only_toast():
    assert parse_toast(["Sooraj", "\n\t\t\t"]) == Toast("Sooraj", None)


def test_parse_none_when_all_blank():
    assert parse_toast(["", "  \n"]) is None


A, B = Toast("a", None), Toast("b", "hi")


def test_existing_toasts_at_startup_are_ignored():
    t = NewToastTracker()
    assert t.update([(1, A), (2, B)]) == []


def test_new_toasts_reported_once():
    t = NewToastTracker()
    t.update([(1, A)])
    assert t.update([(1, A), (2, B)]) == [B]
    assert t.update([(1, A), (2, B)]) == []


def test_dismissed_toasts_do_not_resurface():
    t = NewToastTracker()
    t.update([(1, A)])
    assert t.update([]) == []
    assert t.update([(3, B)]) == [B]


def test_unreadable_toast_is_skipped():
    t = NewToastTracker()
    t.update([])
    assert t.update([(5, None)]) == []


OLD, NEW = "xyz.block.buzz.app", "xyz.block.buzz.desktop"


def test_parse_new_app_layout_without_filler():
    # Buzz Foundation sends [title, body] with no blank line between.
    assert parse_toast(["Sooraj in #backend · AE", "deploy failed"], app=NEW) == Toast(
        "Sooraj in #backend · AE", "deploy failed", NEW
    )


def test_tracker_keys_on_app_and_id():
    t = NewToastTracker()
    t.update([((OLD, 5), A)])
    # Same numeric ID from the other app is a different notification.
    assert t.update([((OLD, 5), A), ((NEW, 5), B)]) == [B]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_same_message_from_both_apps_is_forwarded_once():
    clock = Clock()
    f = CrossAppDuplicateFilter(clock=clock)
    assert f.allow(Toast("Sooraj", "deploy failed", OLD))
    clock.now += 1
    assert not f.allow(Toast("Sooraj in #backend · AE", "deploy failed", NEW))


def test_repeats_within_one_app_still_go_through():
    f = CrossAppDuplicateFilter(clock=Clock())
    assert f.allow(Toast("Sooraj", "ok", OLD))
    assert f.allow(Toast("Maitreyi", "ok", OLD))


def test_same_text_from_other_app_after_window_goes_through():
    clock = Clock()
    f = CrossAppDuplicateFilter(window=10, clock=clock)
    assert f.allow(Toast("Sooraj", "ok", OLD))
    clock.now += 11
    assert f.allow(Toast("Sooraj in #backend · AE", "ok", NEW))
