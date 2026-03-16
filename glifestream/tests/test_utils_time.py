import datetime
from glifestream.utils.time import mtime, from_rfc3339, pn_month_start


def test_mtime():
    # Test with string
    dt_str = '2023-10-27 10:00:00'
    dt = mtime(dt_str)
    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 27
    assert dt.hour == 10
    assert dt.tzinfo == datetime.timezone.utc


def test_from_rfc3339():
    rfc_str = '2023-10-27T10:00:00Z'
    dt = from_rfc3339(rfc_str)
    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 27
    assert dt.tzinfo == datetime.timezone.utc


def test_pn_month_start():
    dt = datetime.datetime(2023, 10, 15)
    prev, nxt = pn_month_start(dt)
    assert prev == datetime.date(2023, 9, 1)
    assert nxt == datetime.date(2023, 11, 1)

    # Test year boundary
    dt_jan = datetime.datetime(2023, 1, 15)
    prev, nxt = pn_month_start(dt_jan)
    assert prev == datetime.date(2022, 12, 1)
    assert nxt == datetime.date(2023, 2, 1)
