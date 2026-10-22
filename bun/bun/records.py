"""A small record decorator.

The standard library `dataclass` builds its `__init__` with `exec`, which
costs about a millisecond per class. The language has 35 node types and a
token type, so the standard library costs more than a third of the startup
time of the language.

This module builds the same `__init__` without `exec`: the fields are read
from the annotations of the class and the constructor is a closure over
them. The behaviour matches the standard library for the way the language
uses it: positional and keyword arguments, defaults, and a default that is
built anew for every instance.
"""

_MISSING = object()


class _Factory:
    """A default value that is built for every instance."""

    __slots__ = ("func",)

    def __init__(self, func):
        self.func = func

    def __call__(self):
        return self.func()


def field(default_factory):
    """Declare a default that is built anew for every instance."""
    return _Factory(default_factory)


def record(cls):
    """Turn a class with annotations into a record.

    The annotations of the class are the fields, in the order they are
    written. A field with a default may be left out; a field with a
    `field(...)` default gets a fresh value for every instance.
    """
    fields = []
    for name in cls.__dict__.get("__annotations__", {}):
        if name.startswith("_"):
            continue
        fields.append((name, cls.__dict__.get(name, _MISSING)))

    def __init__(self, *args, **kwargs):
        if len(args) > len(fields):
            raise TypeError("%s() takes at most %d arguments (%d given)"
                            % (cls.__name__, len(fields), len(args)))
        values = {}
        for index, (name, default) in enumerate(fields):
            if index < len(args):
                if name in kwargs:
                    raise TypeError("%s() got multiple values for argument "
                                    "'%s'" % (cls.__name__, name))
                values[name] = args[index]
            elif name in kwargs:
                values[name] = kwargs.pop(name)
            elif isinstance(default, _Factory):
                values[name] = default()
            elif default is not _MISSING:
                values[name] = default
            else:
                raise TypeError("%s() missing required argument: '%s'"
                                % (cls.__name__, name))
        if kwargs:
            raise TypeError("%s() got an unexpected keyword argument '%s'"
                            % (cls.__name__, next(iter(kwargs))))
        for name, _ in fields:
            object.__setattr__(self, name, values[name])

    def __repr__(self):
        parts = ["%s=%r" % (name, getattr(self, name)) for name, _ in fields]
        return "%s(%s)" % (cls.__name__, ", ".join(parts))

    def __eq__(self, other):
        if other.__class__ is not self.__class__:
            return NotImplemented
        for name, _ in fields:
            if getattr(self, name) != getattr(other, name):
                return False
        return True

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    cls.__init__ = __init__
    cls.__repr__ = __repr__
    cls.__eq__ = __eq__
    cls.__ne__ = __ne__
    cls.__record_fields__ = tuple(name for name, _ in fields)
    return cls


def fields(cls):
    """The names of the fields of a record class, in order."""
    return getattr(cls, "__record_fields__", ())


def is_record(value):
    """Report whether a value is an instance of a record class."""
    return hasattr(type(value), "__record_fields__")
