import uuid

import pytest


@pytest.fixture(scope="session")
def make_required_args():
    def f():
        return [
            "--name",
            "test-transfer-command",
            "--interval",
            "600",
            "--source-endpoint",
            str(uuid.uuid4()),
            "--dest-endpoint",
            str(uuid.uuid4()),
            "--item",
            "/file_a",
            "/file_b",
            "false",
        ]

    return f


@pytest.fixture
def mock_transfer_functions(monkeypatch):
    def f():
        monkeypatch.setattr("timer_cli.main.error_if_not_activated", lambda _: None)
        monkeypatch.setattr(
            "timer_cli.main._get_required_data_access_scopes",
            lambda _, _1: [
                "https://auth.globus.org/scopes/{str(uuid.uuid4())}/data_access"
            ],
        )

    return f
