"""Task registry and structured concurrency groups.

Every spawned task is tracked in a global registry so that ``task_join``
and ``task_done`` can find it again.  A *task group* is the runtime half of
the ``scope`` statement: tasks that are spawned while a group is active
belong to that group, and the group joins every one of its children before
the scope exits.
"""

import threading

from .values import BunDict
from .errors import BunRuntimeError

_TASKS = {}
_TASK_LOCK = threading.Lock()
_NEXT_TASK = [0]

# The group of the thread that is currently running.  Spawned tasks inherit
# the group of their parent, so a task that spawns further tasks keeps them
# all inside the same group.
_TASK_STATE = threading.local()


class TaskGroup:
    """A group of child tasks that must all finish before the scope ends."""

    def __init__(self):
        self.records = []
        self.lock = threading.Lock()

    def add(self, record):
        with self.lock:
            self.records.append(record)


def current_group():
    """Return the task group of the running thread, if there is one."""
    return getattr(_TASK_STATE, "group", None)


def current_task():
    """Return the record of the task running in this thread, if any."""
    return getattr(_TASK_STATE, "current", None)


def set_current_task(record):
    _TASK_STATE.current = record


def set_current_group(group):
    _TASK_STATE.group = group


def scope_enter():
    """Open a task group and return its state.

    The state holds the new group and the group it replaced, so that
    ``scope_exit`` can restore the previous one.
    """
    group = TaskGroup()
    previous = current_group()
    set_current_group(group)
    return (group, previous)


def scope_exit(state):
    """Close a task group, join every child and return the first error.

    The error is returned instead of raised so that the caller can decide
    whether the error of the scope body or the error of a child wins.
    """
    group, previous = state
    set_current_group(previous)
    first_error = None
    for record in list(group.records):
        thread = record.get("thread")
        if thread is not None:
            thread.join()
        if first_error is None and record.get("error") is not None:
            first_error = record["error"]
    return first_error


def as_runtime_error(error):
    """Convert an arbitrary task failure into a runtime error."""
    if isinstance(error, BunRuntimeError):
        return error
    return BunRuntimeError("task failed: %s" % error)


def new_task_id():
    with _TASK_LOCK:
        task_id = _NEXT_TASK[0]
        _NEXT_TASK[0] += 1
        return task_id


def register_task(record):
    with _TASK_LOCK:
        _TASKS[record["id"]] = record
    group = current_group()
    if group is not None:
        group.add(record)
    return record


def lookup_task(task_id):
    return _TASKS.get(task_id)


def task_handle(record):
    handle = BunDict()
    handle.set("id", record["id"])
    return handle
