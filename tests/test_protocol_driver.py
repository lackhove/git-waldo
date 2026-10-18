"""The driver speaks git's helper protocol and keeps the three streams separate."""

from __future__ import annotations


def test_list_advertises_head_and_the_real_oid(driver, stub_oid):
    result = driver.list()

    result.assert_exit(0)
    result.assert_stdout_lines("@refs/heads/main HEAD", f"{stub_oid} refs/heads/main", "")
    result.assert_stderr_empty()
    assert result.stdin == "list\n"


def test_list_for_push_also_advertises_the_real_oid(driver, stub_oid):
    result = driver.list(for_push=True)

    result.assert_exit(0)
    result.assert_stdout_lines("@refs/heads/main HEAD", f"{stub_oid} refs/heads/main", "")
    assert "?" not in result.stdout


def test_fetch_batch_is_acknowledged_with_one_blank_line(driver, stub_oid):
    result = driver.fetch(f"{stub_oid} refs/heads/main")

    result.assert_exit(0)
    result.assert_stdout_lines("")
    assert result.stdin == f"fetch {stub_oid} refs/heads/main\n\n"


def test_push_batch_reports_one_status_per_ref(driver):
    result = driver.push(
        "refs/heads/main:refs/heads/main",
        "refs/heads/other:refs/heads/other",
    )

    result.assert_exit(0)
    result.assert_stdout_lines("ok refs/heads/main", "ok refs/heads/other", "")


def test_option_answers_supported_and_unsupported(driver):
    supported = driver.option("dry-run", "true")
    unsupported = driver.option("progress", "false")

    supported.assert_stdout_lines("ok")
    unsupported.assert_stdout_lines("unsupported")
    supported.assert_exit(0)
    unsupported.assert_exit(0)


def test_capabilities_are_read_from_stdout(driver):
    result = driver.capabilities()

    result.assert_stdout_lines("fetch", "push", "option", "")


def test_a_batch_can_feed_several_protocol_commands(driver, stub_oid):
    result = driver.run("capabilities", "list")

    result.assert_stdout_lines(
        "fetch",
        "push",
        "option",
        "",
        "@refs/heads/main HEAD",
        f"{stub_oid} refs/heads/main",
        "",
    )


def test_stdout_and_stderr_and_exit_code_are_asserted_independently(driver):
    result = driver.with_env(STUB_HELPER_MODE="both").list()

    assert result.exit_code == 4
    assert result.stdout == "stub stdout\n"
    assert result.stderr == "stub stderr\n"
    result.assert_stdout_lines("stub stdout")
    result.assert_stderr_lines("stub stderr")
    result.assert_exit(4)


def test_protocol_failure_is_reported_on_stderr_with_nonzero_exit(driver):
    result = driver.with_env(STUB_HELPER_MODE="fail").list()

    assert result.exit_code == 3
    assert result.stdout == ""
    assert result.stderr == "stub: simulated failure\n"


def test_unknown_protocol_command_fails_loudly(driver):
    result = driver.run("bogus")

    assert result.exit_code == 2
    assert "bogus" in result.stderr
    assert result.stdout == ""


def test_exact_stdin_can_be_fed(driver, stub_oid):
    result = driver.run_input(f"list\nfetch {stub_oid} refs/heads/main\n\n")

    result.assert_stdout_lines("@refs/heads/main HEAD", f"{stub_oid} refs/heads/main", "", "")
