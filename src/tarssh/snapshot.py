"""Build the snapshot commit that records the target's state."""

from __future__ import annotations

from tarssh.descriptor import Descriptor
from tarssh.gitcmd import GitStore
from tarssh.target import Target

MAIN_REF = "refs/heads/main"


def remote_ref(remote: str) -> str:
    return f"refs/remotes/{remote}/main"


def snapshot(
    store: GitStore,
    target: Target,
    descriptor: Descriptor,
    remote: str,
) -> str:
    """Return the oid to advertise for ``refs/heads/main``.

    Ticket 02 builds the empty tree only; ticket 03 fills the entries from the
    target through the fence. The parent and skip rule are already real: a
    clean target must never move the remote branch.
    """
    target.check()
    tree = store.write_tree()
    parent = store.ref(remote_ref(remote))
    if parent is not None and store.tree_of(parent) == tree:
        return parent
    parents = [parent] if parent is not None else []
    subject = f"snapshot of {descriptor.host}:{descriptor.path}"
    return store.commit(tree, parents, subject)
