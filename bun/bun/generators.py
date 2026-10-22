"""The generators of the language.

A generator is a function that gives its values one at a time. The
program that made it asks for the next value, and the function wakes up
where it left off.

The body of a generator runs in a thread of its own, so that it can wait
for the program while the program waits for it.  The values travel
through two queues: one carries the values of the generator to the
program, the other carries the values the program sends back.

The handshake is the one of Python: a value is only asked for when the
program asks for it, so a generator never runs ahead of the program that
reads it.  The program hands the value of the resume to the generator
when it asks for the next one, and the generator stays still until then.
"""

import queue
import threading

from .errors import BunRuntimeError

# The end of a generator. It is put in the outbox when the body is done.
DONE = object()

# No value yet. It tells an empty slot from a value of null.
EMPTY = object()


class Generator:
    """A value that gives its items one at a time.

    The `run` function is called with the generator itself, and it calls
    `generator.yield_value(value)` to give a value to the program and to
    wait for the next one.
    """

    def __init__(self, run, name="<generator>"):
        self.name = name
        self.outbox = queue.Queue()
        self.condition = threading.Condition()
        # The value the generator is waiting for. It is empty when the
        # generator waits for the program.
        self.resume = EMPTY
        # A value that the program sent before the generator reached its
        # first yield.
        self.pending = EMPTY
        # The generator waits for the program.
        self.waiting = False
        self.finished = False
        self.started = False
        self.result = None
        self._run = run
        self._thread = None

    # The thread of the body.

    def _body(self):
        try:
            self._run(self)
        except BaseException as error:      # noqa: BLE001 - the error
            # belongs to the program that asked for the next value.
            self.outbox.put(error)
        else:
            self.outbox.put(DONE)

    def start(self):
        """Start the body of the generator, if it is not running."""
        if self.started:
            return
        self.started = True
        self._thread = threading.Thread(target=self._body, daemon=True)
        self._thread.start()

    def yield_value(self, value):
        """Give a value to the program and wait for the next one.

        The value the program sends back is the answer of the `yield`
        expression.
        """
        self.outbox.put(value)
        with self.condition:
            if self.pending is not EMPTY:
                # The program sent a value before the generator reached
                # its first yield.
                answer = self.pending
                self.pending = EMPTY
                return answer
            self.waiting = True
            while self.resume is EMPTY:
                self.condition.wait()
            answer = self.resume
            self.resume = EMPTY
            self.waiting = False
            return answer

    def finish(self, value):
        """The body of the generator is done, and it returns a value."""
        self.result = value
        self.finished = True

    def _resume(self, value):
        """Let the generator go on with a value.

        The generator only goes on when it waits for the program, so it
        never runs ahead of the program that reads it.
        """
        with self.condition:
            if not self.waiting:
                return False
            self.waiting = False
            self.resume = value
            self.condition.notify_all()
            return True

    def _wait(self):
        """Wait for the next value of the generator."""
        self.start()
        item = self.outbox.get()
        if item is DONE:
            self.finished = True
            raise StopIteration()
        if isinstance(item, BaseException):
            self.finished = True
            raise item
        return item

    def next_value(self):
        """The next value of the generator.

        A generator that is over has no next value, and that is an
        error.
        """
        if self.finished:
            raise BunRuntimeError("the generator is over")
        self._resume(None)
        try:
            return self._wait()
        except StopIteration:
            raise BunRuntimeError("the generator is over")

    def send(self, value):
        """Resume the generator with a value.

        The value is the answer of the `yield` expression that is
        waiting.
        """
        if self.finished:
            raise BunRuntimeError("the generator is over")
        if not self._resume(value):
            # The generator has not reached its first yield yet, so the
            # value waits there.
            with self.condition:
                self.pending = value
        try:
            return self._wait()
        except StopIteration:
            raise BunRuntimeError("the generator is over")

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self.next_value()
        except BunRuntimeError:
            raise StopIteration()

    def __repr__(self):
        return "<generator %s>" % self.name


def is_generator(value):
    """Is the value a generator?"""
    return isinstance(value, Generator)
