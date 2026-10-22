"""The capability sandbox.

A capability manifest says what a piece of code may do. The runtime
checks the manifest before every network call, every file access and
every process spawn that the sandboxed code makes.

A manifest grants, it does not forbid: a capability that is not named in
the manifest is not allowed. The default is therefore the safe one, and a
program that wants a capability has to ask for it by name.
"""

import os
import threading
from urllib.parse import urlparse

from .errors import BunRuntimeError

_state = threading.local()

NET = "net"
FS = "fs"
EXEC = "exec"
CLOCK = "clock"


def policies():
    """The stack of manifests that are in force on this thread."""
    return getattr(_state, "policies", None) or []


def enter(policy):
    """Push a manifest onto the stack."""
    if policy is None:
        raise BunRuntimeError("sandbox_enter() expects a manifest")
    stack = policies()
    stack.append(policy)
    _state.policies = stack
    return None


def leave():
    """Pop the manifest that is in force."""
    stack = policies()
    if stack:
        stack.pop()
    return None


def active():
    """The manifest that is in force, or None when the code is not sandboxed."""
    stack = policies()
    if not stack:
        return None
    return stack[-1]


def _entries(policy, name):
    value = policy.get(name)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def _host_matches(host, entry):
    if entry == host:
        return True
    if entry.startswith(".") and host.endswith(entry):
        return True
    return False


def _path_allowed(path, entry):
    root = os.path.abspath(entry)
    full = os.path.abspath(path)
    if full == root:
        return True
    return full.startswith(root + os.sep)


def check_net(host):
    """Check that the sandboxed code may reach `host`."""
    policy = active()
    if policy is None:
        return
    for entry in _entries(policy, NET):
        if _host_matches(host, entry):
            return
    raise BunRuntimeError(
        "sandbox: the network host '%s' is not allowed" % host)


def check_net_url(url):
    """Check that the sandboxed code may reach the host of `url`."""
    if not isinstance(url, str):
        return
    host = urlparse(url).hostname
    if host:
        check_net(host)


def check_fs(path):
    """Check that the sandboxed code may touch `path`."""
    policy = active()
    if policy is None:
        return
    for entry in _entries(policy, FS):
        if _path_allowed(path, entry):
            return
    raise BunRuntimeError(
        "sandbox: the path '%s' is not allowed" % path)


def check_exec():
    """Check that the sandboxed code may start a process."""
    policy = active()
    if policy is None:
        return
    if policy.get(EXEC) is True:
        return
    raise BunRuntimeError("sandbox: starting a process is not allowed")


def check_clock():
    """Check that the sandboxed code may read the clock."""
    policy = active()
    if policy is None:
        return
    if policy.get(CLOCK) is True:
        return
    raise BunRuntimeError("sandbox: reading the clock is not allowed")
