# Test harness

Everything here is test infrastructure. The helper under test is supplied by
the test, so the same harness serves both the stub helper and the real
`tarssh.remote`.

## Fixtures (`conftest.py`)

| fixture | what it gives you |
|---|---|
| `target` | `Target` at a temp path; `create()`, `populate({...})`, `empty()`, `remove()`, `make_unreadable()`, `restore()`, `read()`, `write()`, `symlink()`, `url()` |
| `fake_ssh` | `FakeSSH`; `env()`, `url`, `run_remote()`, `run_ssh()`, `run_client()`, `calls`, `forbidden`, `failures`, `fail_connection()`, `fail_extraction()`, `fail_removal()`, `restore()` |
| `make_driver` | builds a `ProtocolDriver` for any argv; defaults to the stub helper |
| `driver` | `ProtocolDriver` for `tests/stub_helper.py` |
| `helper_env` | `os.environ` with the fake SSH shim first on `PATH` |
| `git_env` | `helper_env` plus `TARSSH_HELPER`, for real `git` commands |
| `stub_command` / `stub_oid` | the stub helper argv and the oid it advertises |
| `real_helper` | argv for the real helper: `python -m tarssh.remote` |
| `tarssh_env` | `fake_ssh.env()` with every `TARSSH_*` override removed |
| `real_git_env` | `tarssh_env` plus `TARSSH_HELPER=module:tarssh.remote` |

## Using it

```python
def test_list(driver, stub_oid):
    result = driver.list()          # also .list(for_push=True), .fetch(), .push(), .option()
    result.assert_exit(0)
    result.assert_stdout_lines("@refs/heads/main HEAD", f"{stub_oid} refs/heads/main", "")
    result.assert_stderr_empty()

def test_real_helper(make_driver):
    driver = make_driver([sys.executable, "-m", "tarssh.remote"])
    ...
```

The target's `PATH` holds only `find`, `tar`, `rm`, `mkdir`, `xargs` and
`sha1sum`; shell builtins work. Anything else, or a non-busybox option, exits
non-zero and lands in `fake_ssh.forbidden` naming the command or option. The
option allowlists live in `busybox_guard.py`; extend them when a legitimate
busybox flag starts a failing test.

`fake_ssh.run_remote("find ...")` exercises the seam directly. Helpers find it
through `fake_ssh.env()`: `ssh`, `scp`, `sftp`, `rsync` and
`git-remote-tarssh` shims live in `fake_ssh.client_bin`.

`git_env` is enough for `git ls-remote <target.url>`; `TARSSH_HELPER` is either
a command line or `module:tarssh.remote`.
