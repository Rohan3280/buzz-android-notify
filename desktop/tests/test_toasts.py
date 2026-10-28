from aebuzz_desktop.toasts import NewToastTracker, Toast, parse_toast


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
