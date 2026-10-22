from .errors import BunRuntimeError


class Environment:
    def __init__(self, parent=None):
        self.parent = parent
        self.values = {}

    def define(self, name, value, mutable):
        self.values[name] = [value, mutable]

    def get(self, name):
        env = self
        while env is not None:
            if name in env.values:
                return env.values[name][0]
            env = env.parent
        raise BunRuntimeError("undefined variable '%s'" % name)

    def assign(self, name, value):
        env = self
        while env is not None:
            if name in env.values:
                if not env.values[name][1]:
                    raise BunRuntimeError("cannot assign to immutable variable '%s'" % name)
                env.values[name][0] = value
                return
            env = env.parent
        raise BunRuntimeError("undefined variable '%s'" % name)

    def delete(self, name):
        """Remove a name from the scope that holds it."""
        env = self
        while env is not None:
            if name in env.values:
                del env.values[name]
                return
            env = env.parent
        raise BunRuntimeError("undefined variable '%s'" % name)
