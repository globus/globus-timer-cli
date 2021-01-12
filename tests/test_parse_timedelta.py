from datetime import timedelta
import pytest

from timer_cli.main import _parse_timedelta

test_cases = [
    ("", timedelta(seconds=0)),
    ("      ", timedelta(seconds=0)),
    ("0", timedelta(seconds=0)),
    ("0s", timedelta(seconds=0)),
    ("0   s", timedelta(seconds=0)),
    ("10", timedelta(seconds=10)),
    ("100", timedelta(seconds=100)),
    ("5m 10s", timedelta(minutes=5, seconds=10)),
    ("5m 100s", timedelta(minutes=5, seconds=100)),
    ("2h 3m 4s", timedelta(hours=2, minutes=3, seconds=4)),
    ("2h3m4s", timedelta(hours=2, minutes=3, seconds=4)),
    ("2h     3m   4s", timedelta(hours=2, minutes=3, seconds=4)),
    ("10h", timedelta(hours=10)),
]


@pytest.mark.parametrize("s,d", test_cases)
def test_parse_timedelta(s, d):
    assert _parse_timedelta(s) == d
