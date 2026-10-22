# The project is called git-waldo; the scheme is waldo

Status: accepted

The project was previously called `tarssh`, which names its two implementation
details — tar and SSH — and neither the interface nor the outcome. Read cold, it
suggests a backup or transport utility for tar over SSH, not a git remote
helper that deploys a config repo to an appliance. The name sits one layer
below the value: tar and SSH are exactly what the documentation promises the
operator will never have to think about. It also collides with an existing SSH
tarpit of the same name in a neighbouring ecosystem, which muddies search
results.

We renamed the project to **git-waldo** and the interface to **waldo**. A
*waldo* is the established term for a remote manipulator: a device that copies
the movements of a human operator, with no autonomy of its own. The operator
stays at the workstation; the machine has no local intelligence. That is the
relationship this tool implements between the config repo and the appliance.

## Naming criteria

- **The project name carries git; the scheme carries the remote object; the
  tagline carries the category.** `git-waldo` says what ecosystem it belongs
  to. `waldo://` is the short thing an operator types.
- **The remote object is a human-controlled machine, not an agent.** A waldo
  does not decide anything. The tool therefore never implies that git, an
  agent, or a daemon runs on the appliance.
- **The name must never claim fleet orchestration.** One config repo has one
  target. `waldo` is singular and does not suggest a swarm.
- **The scheme is the irreversible choice.** The distribution, import package,
  executable, descriptor and environment prefix can change while unpublished.
  Once a URL scheme is released, it is permanent.
- **The name must be safe to say.** No class, ethnic, sexual or other
  pejorative association may attach to it in English or German.

## Surface

| Thing | Name |
|---|---|
| distribution | `git-waldo` |
| import and wheel package | `waldo` |
| executable | `git-remote-waldo` |
| URL scheme | `waldo://`, `waldo::` |
| environment overrides | `WALDO_*` |
| descriptor | `.waldo.toml` |
| example descriptor | `.waldo.example.toml` |
| target lock | `/tmp/waldo-<hash>.lock` |
| snapshot ident | `waldo <waldo@localhost>` |
| agent skill | `skills/waldo/` |

The distribution and import package deliberately differ. The distribution name
helps discovery and says “git”; the package, scheme, descriptor and environment
all use the short interface name. This is ordinary Python packaging, not a
compatibility layer.

## Considered options

- **Keep `tarssh`.** Rejected: it names the mechanism the tool exists to hide,
  reads as a tar transport rather than a git remote helper, and collides with an
  unrelated same-domain project.
- **`telechir`** — the exact robotics term for a remotely controlled robot.
  Rejected: awkward to pronounce and visually unappealing, despite an excellent
  meaning.
- **`telefactor`, `telerobot`, `telepresence`.** Rejected: correct but clinical;
  they describe the mechanism rather than the relationship.
- **`waldo` alone.** Rejected as the package name: PyPI and crates.io already
  use it, and “Where's Waldo?” dominates search. It remains the scheme because
  transport names have no package registry and the word is short and exact.
- **`git-waldo` as the URL scheme.** Rejected: git looks for
  `git-remote-git-waldo`, a double-git stutter. The `git-` belongs in the
  project name, not the transport name.

## Consequences

- There is no compatibility shim: no `git-remote-tarssh`, no `tarssh://` alias,
  and no reader for `.tarssh.toml`. An old descriptor alone produces a named
  migration error.
- A remote still pointing at `tarssh::` fails at git's transport lookup because
  no `git-remote-tarssh` exists. The migration runbook is the remedy.
- The target-side lock path changes. An old and a new helper do not exclude each
  other, so migration starts by confirming that no push is in flight.
- Existing snapshot commits are not rewritten. Snapshots created after this
  rename carry `waldo <waldo@localhost>`; the skip rule compares trees and is
  unaffected.
- The version stays `0.1.0`. Publishing and reserving the name are separate,
  deliberate decisions.
