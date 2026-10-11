from gway_rfid.core import Tag
from gway_rfid.presence import PresenceTracker


def tag(uid):
    return Tag(bytes.fromhex(uid))


def test_hold_and_represent():
    tracker = PresenceTracker(1.2)
    assert [e.kind for e in tracker.observe(tag("AABB"), 0)] == ["scanned"]
    assert tracker.observe(tag("AABB"), 0.1) == []
    assert tracker.observe(None, 0.5) == []
    assert tracker.observe(tag("AABB"), 0.8) == []
    assert tracker.observe(None, 1.0) == []
    assert [e.kind for e in tracker.observe(None, 2.1)] == ["removed"]
    assert [e.generation for e in tracker.observe(tag("AABB"), 2.2)] == [2]


def test_swap_without_gap():
    tracker = PresenceTracker()
    tracker.observe(tag("AABB"), 0)
    events = tracker.observe(tag("CCDD"), 0.1)
    assert [(e.kind, e.uid) for e in events] == [
        ("removed", "AABB"), ("scanned", "CCDD")
    ]


def test_missed_polls_do_not_duplicate():
    tracker = PresenceTracker()
    tracker.observe(tag("AABB"), 0)
    assert tracker.observe(None, 0.4) == []
    assert tracker.observe(None, 0.9) == []
    assert tracker.observe(tag("AABB"), 1.0) == []
