import datetime
from unittest.mock import MagicMock
import uuid

import pytest

from timer_cli.job import job_submit


@pytest.fixture
def mock_job_submit(monkeypatch):
    def f(*args, **kwargs):
        job_submit_data = {
            "status_code": 201,
            "json": lambda: {
                "name": "fake-job-name",
                "job_id": str(uuid.uuid4()),
                "status": "loaded",
                "start": str(datetime.datetime.now().isoformat()),
                "interval": 600,
            },
        }
        job_submit_response = type("FakeJobResponse", (object,), job_submit_data)
        mocked_job_submit = MagicMock(
            job_submit, *args, return_value=job_submit_response, **kwargs
        )
        monkeypatch.setattr("timer_cli.main.job_submit", mocked_job_submit)
        return mocked_job_submit

    return f
