# Git-side remote-helper protocol

Verified against git 2.56 while building tickets 01-02. Target-side transport
facts live in `AGENTS.md`; this file is about what git sends and expects.
The executable driver is `tests/harness.py`; see `tests/README.md`.

- `capabilities` is always git's first stdin command. Answer with `fetch`,
  `push`, `option`, then a blank line. Do not print capabilities unsolicited.
- `waldo::` arrives as `<remote> ""`; `waldo://...` arrives as
  `<remote> <url>`. A bare `waldo:` never reaches the helper.
- Fetch sends `list`, then `fetch <oid> <name>` lines in a batch ending with a
  blank line. The snapshot objects are written during `list`; answer the fetch
  batch with one blank line. `git clone` always sends `fetch`; a normal fetch
  may not.
- `list` prints `@refs/heads/main HEAD`, `<real oid> refs/heads/main`, blank.
  `?` means "value unknown" and leaves the oid null; never use it for an object
  that exists.
- Push sends `list for-push` before the `push` lines. An absent remote branch
  is advertised as no refs (branch creation); an existing branch as its real
  oid. The push line carries `[+]<src>:<dst>` and no old oid, so the helper
  remembers the advertised oid in-process.
- Push status is one `ok <dst>` or `error <dst> <why>` per ref, then a blank
  line. Ref rejections exit 0; transport failures exit non-zero.
- Advertise `option` for `--dry-run`; answer `ok` or `unsupported`.
  `git push --dry-run` still sends push lines; simulate them.
- The helper never writes `refs/remotes/*`; git owns those.
- `git archive` 2.56 has no `--pathspec-from-file`: pass paths after `--` and
  chunk to stay under ARG_MAX.
- Stdout is protocol only; operator output goes to stderr.
