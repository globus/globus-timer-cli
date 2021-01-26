from click.testing import CliRunner

from timer_cli.main import cli


def test_missing_transfer_options():
    result = CliRunner().invoke(cli, ["job", "transfer"])
    assert result.exit_code == 2, result
    assert "Error" in result.stdout, result.stdout


def test_transfer_options(
    mock_transfer_functions,
    mock_job_submit,
    make_required_args,
):
    mock_transfer_functions()
    job_submit = mock_job_submit()
    test_label = "test-label"
    sync_level = 0
    result = CliRunner().invoke(
        cli,
        [
            "job",
            "transfer",
            *make_required_args(),
            "--label",
            test_label,
            "--sync-level",
            sync_level,
            "--encrypt-data",
            "--verify-checksum",
            "--preserve-timestamp",
        ],
    )
    assert result.exit_code == 0, result
    expect_callback_body = {
        "label": test_label,
        "sync_level": sync_level,
        "encrypt_data": True,
        "verify_checksum": True,
        "preserve_timestamp": True,
    }
    call_body = job_submit.call_args.kwargs["callback_body"]["body"]
    for k, v in expect_callback_body.items():
        assert call_body.get(k) == v, job_submit.call_args.kwargs


def test_transfer_option_defaults(
    mock_transfer_functions,
    mock_job_submit,
    make_required_args,
):
    mock_transfer_functions()
    job_submit = mock_job_submit()
    test_label = "test-label"
    sync_level = 0
    result = CliRunner().invoke(
        cli,
        [
            "job",
            "transfer",
            *make_required_args(),
            "--label",
            test_label,
            "--sync-level",
            sync_level,
        ],
    )
    assert result.exit_code == 0, result
    expect_callback_body = {
        "label": test_label,
        "sync_level": sync_level,
        "encrypt_data": False,
        "verify_checksum": False,
        "preserve_timestamp": False,
    }
    call_body = job_submit.call_args.kwargs["callback_body"]["body"]
    for k, v in expect_callback_body.items():
        assert call_body.get(k) == v, job_submit.call_args.kwargs
    assert result.exit_code == 0, result
