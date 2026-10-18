"""Resolve the target descriptor: ``TARSSH_*`` > URL > ``.tarssh.toml`` > defaults.

The four layers describe one target. Each field is resolved independently so a
one-off override (``TARSSH_SSH_PORT=22222``) can combine with a committed host
and directory.
"""

from __future__ import annotations

import getpass
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.parse import unquote, urlsplit

from tarssh.errors import ProtocolError
from tarssh.gitcmd import git_output

TOML_NAME = ".tarssh.toml"
DEFAULT_PORT = 22
ENV_FIELDS = {
    "user": "TARSSH_USER",
    "host": "TARSSH_HOST",
    "ssh_port": "TARSSH_SSH_PORT",
    "dir": "TARSSH_DIR",
}


@dataclass(frozen=True)
class UrlTarget:
    """The fields a ``tarssh://`` URL carries explicitly."""

    user: str | None
    host: str
    port: int | None
    path: str | None


@dataclass(frozen=True)
class Descriptor:
    """A fully resolved target."""

    user: str
    host: str
    port: int
    path: str
    url: str

    def label(self) -> str:
        return f"{self.user}@{self.host}:{self.port}:{self.path}"


@dataclass(frozen=True)
class Resolved:
    descriptor: Descriptor
    warnings: tuple[str, ...]


def parse_remote_url(url: str) -> UrlTarget | None:
    """Parse ``tarssh://`` or the descriptor-only ``tarssh::`` form.

    A bare ``tarssh:`` is not a helper URL: git parses it as scp-like syntax and
    tries to SSH to a host called ``tarssh``. We refuse it rather than guessing.
    """
    if url in ("", "tarssh::"):
        return None
    if not url.startswith("tarssh://"):
        raise ProtocolError(
            f"not a tarssh helper URL: {url!r} (use tarssh://... or tarssh::)"
        )

    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as error:
        raise ProtocolError(f"invalid URL {url}: {error}") from error
    if parts.scheme != "tarssh":
        raise ProtocolError(f"unsupported URL scheme in {url!r}")
    if not host:
        raise ProtocolError(f"missing host in URL: {url}")
    path = unquote(parts.path)
    if not path:
        raise ProtocolError(f"missing absolute target path in URL: {url}")
    if not path.startswith("/"):
        raise ProtocolError(f"target path is not absolute in URL {url}: {path!r}")
    user = unquote(parts.username) if parts.username else None
    return UrlTarget(user=user, host=host, port=port, path=path)


def repository_root(cwd: Path | None = None) -> Path | None:
    """The config repo root, found with git, never inferred from the cwd."""
    completed = git_output(["rev-parse", "--show-toplevel"], cwd)
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return Path(root) if root else None


def read_toml(root: Path) -> tuple[dict[str, object], Path | None]:
    """Read the committed descriptor. Missing is not an error."""
    path = root / TOML_NAME
    if not path.is_file():
        return {}, None
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProtocolError(f"cannot read {path}: {error}") from error

    fields: dict[str, object] = {}
    for key in ("user", "host", "dir"):
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ProtocolError(f"{path}: {key} must be a string")
        fields[key] = value
    port = data.get("ssh_port")
    if port is not None:
        if not isinstance(port, int) or isinstance(port, bool):
            raise ProtocolError(f"{path}: ssh_port must be an integer")
        fields["ssh_port"] = port
    return fields, path


def _environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _value(mapping: Mapping[str, str], name: str) -> str | None:
    value = mapping.get(name)
    return value if value else None


def _port(value: str, url: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise ProtocolError(f"invalid SSH port {value!r} for {url}") from error
    if not 1 <= port <= 65535:
        raise ProtocolError(f"invalid SSH port {value!r} for {url}")
    return port


def _local_username() -> str:
    try:
        return getpass.getuser()
    except OSError:  # pragma: no cover - exotic environments without a passwd entry
        return "root"


def _disagreement_line(
    fields: Mapping[str, object],
    explicit: Mapping[str, object],
    overridden: Mapping[str, bool],
) -> str | None:
    """One line for the URL fields whose effective value contradicts the file.

    A field appears only when the URL carries it explicitly, its effective value
    still comes from the URL (no ``TARSSH_*`` override), and the file says
    something different. Precedence is unchanged; this is reporting only.
    """
    differences = [
        (name, url_value, fields.get(name))
        for name, url_value in explicit.items()
        if url_value is not None
        and fields.get(name) is not None
        and url_value != fields.get(name)
        and not overridden[name]
    ]
    if not differences:
        return None
    url_side = ", ".join(f"{name}={value}" for name, value, _ in differences)
    file_side = ", ".join(f"{name}={value}" for name, _, value in differences)
    return f"using {url_side} from the remote URL; {TOML_NAME} says {file_side}"


def resolve(
    url: str,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Resolved:
    """Resolve every field of the target for one helper invocation."""
    parsed = parse_remote_url(url)
    shown_url = url or "tarssh::"
    fields, _ = read_toml(root) if (root := repository_root(cwd)) else ({}, None)
    env = _environment(environ)

    url_user = parsed.user if parsed else None
    url_host = parsed.host if parsed else None
    url_port = parsed.port if parsed else None
    url_path = parsed.path if parsed else None

    env_user = _value(env, ENV_FIELDS["user"])
    env_host = _value(env, ENV_FIELDS["host"])
    env_port = _value(env, ENV_FIELDS["ssh_port"])
    env_dir = _value(env, ENV_FIELDS["dir"])

    warning = _disagreement_line(
        fields,
        {
            "user": url_user,
            "host": url_host,
            "ssh_port": url_port,
            "dir": url_path,
        },
        {
            "user": env_user is not None,
            "host": env_host is not None,
            "ssh_port": env_port is not None,
            "dir": env_dir is not None,
        },
    )
    warnings = (warning,) if warning is not None else ()

    host = env_host or url_host or fields.get("host")
    if not host:
        raise ProtocolError(
            f"no target host: set TARSSH_HOST, use tarssh://host/..., "
            f"or add host to {TOML_NAME} (URL: {shown_url})"
        )

    user = env_user or url_user or fields.get("user") or _local_username()

    if env_port is not None:
        port = _port(env_port, shown_url)
    elif url_port is not None:
        port = url_port
    elif fields.get("ssh_port") is not None:
        port = int(fields["ssh_port"])
    else:
        port = DEFAULT_PORT

    path = env_dir or url_path or fields.get("dir")
    if not path:
        raise ProtocolError(
            f"no target directory: set TARSSH_DIR or {TOML_NAME} (URL: {shown_url})"
        )
    if not path.startswith("/"):
        raise ProtocolError(
            f"target directory is not absolute: {path!r} (URL: {shown_url})"
        )

    descriptor = Descriptor(
        user=str(user),
        host=str(host),
        port=port,
        path=str(path),
        url=shown_url,
    )
    return Resolved(descriptor=descriptor, warnings=tuple(warnings))


def _prompt(
    stdin: TextIO, stdout: TextIO, label: str, default: str | None
) -> str:
    """Ask once for one field; an empty answer keeps the offered default."""
    shown = f" [{default}]" if default else ""
    stdout.write(f"{label}{shown}: ")
    stdout.flush()
    line = stdin.readline()
    if line == "":
        if default is not None:
            return default
        raise ProtocolError(f"no value for {label}: stdin was closed")
    value = line.strip()
    return value if value else (default or "")


def _confirm(stdin: TextIO, stdout: TextIO, path: Path) -> None:
    stdout.write(f"{path} already exists; overwrite? [y/N]: ")
    stdout.flush()
    answer = stdin.readline().strip().lower()
    if answer not in ("y", "yes"):
        raise ProtocolError(f"{path} not overwritten")


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _existing(fields: Mapping[str, object], name: str, kind: type) -> object | None:
    value = fields.get(name)
    return value if isinstance(value, kind) else None


def write_descriptor(root: Path, *, stdin: TextIO, stdout: TextIO) -> Path:
    """Interactively write ``.tarssh.toml`` at the config repo root.

    Prompts go to ``stdout`` (the caller passes stderr) and answers are read
    line by line, so piped stdin drives the same code path as a terminal.
    Existing values become the offered defaults; refusing to overwrite aborts
    before anything is written.
    """
    path = root / TOML_NAME
    fields, _ = read_toml(root)
    if path.exists():
        _confirm(stdin, stdout, path)

    existing_user = _existing(fields, "user", str)
    existing_host = _existing(fields, "host", str)
    existing_port = _existing(fields, "ssh_port", int)
    existing_dir = _existing(fields, "dir", str)

    user = _prompt(
        stdin,
        stdout,
        "user",
        str(existing_user) if existing_user is not None else _local_username(),
    )
    host = _prompt(
        stdin, stdout, "host", str(existing_host) if existing_host is not None else None
    )
    if not host:
        raise ProtocolError("host must not be empty")

    port_text = _prompt(
        stdin,
        stdout,
        "ssh_port",
        str(existing_port if existing_port is not None else DEFAULT_PORT),
    )
    port = _port(port_text, str(path))

    target_dir = _prompt(
        stdin, stdout, "dir", str(existing_dir) if existing_dir is not None else None
    )
    if not target_dir:
        raise ProtocolError("dir must not be empty")
    if not target_dir.startswith("/"):
        raise ProtocolError(f"dir must be an absolute path: {target_dir!r}")

    content = "\n".join(
        (
            f"user = {_toml_string(user)}",
            f"host = {_toml_string(host)}",
            f"ssh_port = {port}",
            f"dir = {_toml_string(target_dir)}",
        )
    )
    try:
        path.write_text(content + "\n", encoding="utf-8")
    except OSError as error:
        raise ProtocolError(f"cannot write {path}: {error}") from error
    return path
