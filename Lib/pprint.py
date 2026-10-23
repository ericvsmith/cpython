#  Author:      Fred L. Drake, Jr.
#               fdrake@acm.org
#
#  This is a simple little module I wrote to make life easier.  I didn't
#  see anything quite like it in the library, though I may have overlooked
#  something.  I wrote this when I was trying to read some heavily nested
#  tuples with fairly non-descriptive content.  This is modeled very much
#  after Lisp/Scheme - style pretty-printing of lists.  If you find it
#  useful, thank small children who sleep at night.

"""Support to pretty-print lists, tuples, & dictionaries recursively.

Very simple, but useful, especially in debugging data structures.

Classes
-------

PrettyPrinter()
    Handle pretty-printing operations onto a stream using a configured
    set of formatting parameters.

Functions
---------

pformat()
    Format a Python object into a pretty-printed representation.

pprint()
    Pretty-print a Python object to a stream [default is sys.stdout].

saferepr()
    Generate a 'standard' repr()-like value, but protect against recursive
    data structures.

"""

import collections as _collections
import sys as _sys
import types as _types
from io import StringIO as _StringIO

# The pretty-print protocol of PEP 813.
_PROTOCOL_NAMES = (
    "VALUES", "KWARGS", "ITEMS", "DELEGATE", "LEAF", "Layout", "Keyword",
    "Entry", "BreakableString", "BreakableBytes", "FormattableNumber",
    "DescriptionType", "decompose", "Printer", "Expand",
)

__all__ = ["pprint","pformat","isreadable","isrecursive","saferepr",
           "PrettyPrinter", "pp", *_PROTOCOL_NAMES]


_PROTOCOL_IMPLEMENTATION_NAMES = frozenset({
    *_PROTOCOL_NAMES,
    "_ordered_dict_pprint", "_mapping_view_pprint", "_counter_pprint",
    "_chainmap_pprint", "_user_container_pprint",
})


def __getattr__(name):
    if name in _PROTOCOL_IMPLEMENTATION_NAMES:
        _load_protocol()
        try:
            return globals()[name]
        except KeyError:
            pass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted({*globals(), *_PROTOCOL_NAMES})


def pprint(object, stream=None, indent=1, width=80, depth=None, *,
           compact=False, expand=False, sort_dicts=True,
           underscore_numbers=False):
    """Pretty-print a Python object to a stream [default is sys.stdout]."""
    printer = PrettyPrinter(
        stream=stream, indent=indent, width=width, depth=depth,
        compact=compact, expand=expand, sort_dicts=sort_dicts,
        underscore_numbers=underscore_numbers)
    printer.pprint(object)


def pformat(object, indent=1, width=80, depth=None, *,
            compact=False, expand=False, sort_dicts=True,
            underscore_numbers=False):
    """Format a Python object into a pretty-printed representation."""
    return PrettyPrinter(indent=indent, width=width, depth=depth,
                         compact=compact, expand=expand, sort_dicts=sort_dicts,
                         underscore_numbers=underscore_numbers).pformat(object)


def pp(object, *args, sort_dicts=False, **kwargs):
    """Pretty-print a Python object"""
    pprint(object, *args, sort_dicts=sort_dicts, **kwargs)


def saferepr(object):
    """Version of repr() which can handle recursive data structures."""
    return PrettyPrinter()._safe_repr(object, {}, None, 0)[0]


def isreadable(object):
    """Determine if saferepr(object) is readable by eval()."""
    return PrettyPrinter()._safe_repr(object, {}, None, 0)[1]


def isrecursive(object):
    """Determine if object requires a recursive representation."""
    return PrettyPrinter()._safe_repr(object, {}, None, 0)[2]


class _safe_key:
    """Helper function for key functions when sorting unorderable objects.

    The wrapped-object will fallback to a Py2.x style comparison for
    unorderable types (sorting first comparing the type name and then by
    the obj ids).  Does not work recursively, so dict.items() must have
    _safe_key applied to both the key and the value.

    """

    __slots__ = ['obj']

    def __init__(self, obj):
        self.obj = obj

    def __lt__(self, other):
        try:
            return self.obj < other.obj
        except TypeError:
            return ((str(type(self.obj)), id(self.obj)) < \
                    (str(type(other.obj)), id(other.obj)))


def _safe_tuple(t):
    "Helper function for comparing 2-tuples"
    return _safe_key(t[0]), _safe_key(t[1])


class PrettyPrinter:
    def __init__(self, indent=1, width=80, depth=None, stream=None, *,
                 compact=False, expand=False, sort_dicts=True,
                 underscore_numbers=False):
        """Handle pretty printing operations onto a stream using a set of
        configured parameters.

        indent
            Number of spaces to indent for each level of nesting.

        width
            Attempted maximum number of columns in the output.

        depth
            The maximum depth to print out nested structures.

        stream
            The desired output stream.  If omitted (or false), the standard
            output stream available at construction will be used.

        compact
            If true, several items will be combined in one line.
            Incompatible with expand mode.

        expand
            If true, the output will be formatted similar to
            pretty-printed json.dumps() when ``indent`` is supplied.
            Incompatible with compact mode.

        sort_dicts
            If true, dict keys are sorted.

        underscore_numbers
            If true, digit groups are separated with underscores.

        """
        indent = int(indent)
        width = int(width)
        if indent < 0:
            raise ValueError('indent must be >= 0')
        if depth is not None and depth <= 0:
            raise ValueError('depth must be > 0')
        if not width:
            raise ValueError('width must be != 0')
        if compact and expand:
            raise ValueError('compact and expand are incompatible')
        self._depth = depth
        self._indent_per_level = indent
        self._width = width
        if stream is not None:
            self._stream = stream
        else:
            self._stream = _sys.stdout
        self._compact = bool(compact)
        self._expand = bool(expand)
        self._sort_dicts = sort_dicts
        self._underscore_numbers = underscore_numbers

    def pprint(self, object):
        if self._stream is not None:
            self._format(object, self._stream, 0, 0, {}, 0)
            self._stream.write("\n")

    def pformat(self, object):
        sio = _StringIO()
        self._format(object, sio, 0, 0, {}, 0)
        return sio.getvalue()

    def isrecursive(self, object):
        return self.format(object, {}, 0, 0)[2]

    def isreadable(self, object):
        s, readable, recursive = self.format(object, {}, 0, 0)
        return readable and not recursive

    def _format(self, object, stream, indent, allowance, context, level):
        # Width of any "key: " prefix already written on the current line by
        # _format_child().  In expand mode `indent` is the block indent and so
        # does not include it, but it still consumes width here.
        prefix_len = self._pending_prefix_len
        self._pending_prefix_len = 0
        objid = id(object)
        if objid in context:
            stream.write(_recursion(object))
            self._recursive = True
            self._readable = False
            return
        rep = self._repr(object, context, level)
        max_width = self._width - indent - prefix_len - allowance
        if len(rep) > max_width:
            p = self._dispatch.get(type(object).__repr__, None)
            # Lazy import to improve module import time
            from dataclasses import is_dataclass

            if p is not None:
                context[objid] = 1
                p(self, object, stream, indent, allowance, context, level + 1)
                del context[objid]
                return
            elif (is_dataclass(object) and
                  not isinstance(object, type) and
                  object.__dataclass_params__.repr and
                  # Check dataclass has generated repr method.
                  hasattr(object.__repr__, "__wrapped__") and
                  "__create_fn__" in object.__repr__.__wrapped__.__qualname__):
                context[objid] = 1
                self._pprint_dataclass(object, stream, indent, allowance, context, level + 1)
                del context[objid]
                return
        stream.write(rep)

    def _format_block_start(self, start_str, indent):
        if self._expand:
            return f"{start_str}\n{' ' * indent}"
        return start_str

    def _format_block_end(self, end_str, indent):
        if self._expand:
            return f"\n{' ' * indent}{end_str}"
        return end_str

    def _child_indent(self, indent, prefix_len):
        if self._expand:
            return indent
        return indent + prefix_len

    # Set by _format_child() immediately before it calls _format(), and
    # consumed there.  Passing it out of band keeps _format()'s signature
    # unchanged for third-party subclasses that override it.
    _pending_prefix_len = 0

    def _format_child(self, object, stream, indent, allowance, context, level,
                      prefix_len):
        if self._expand:
            # Aligned mode folds the prefix into the indent (see
            # _child_indent), so only expand mode needs to report it.
            self._pending_prefix_len = prefix_len
        try:
            self._format(object, stream, indent, allowance, context, level)
        finally:
            self._pending_prefix_len = 0

    def _write_indent_padding(self, write):
        if self._expand:
            if self._indent_per_level > 0:
                write(self._indent_per_level * " ")
        elif self._indent_per_level > 1:
            write((self._indent_per_level - 1) * " ")

    def _pprint_dataclass(self, object, stream, indent, allowance, context, level):
        # Lazy import to improve module import time
        from dataclasses import fields as dataclass_fields

        cls_name = object.__class__.__name__
        if self._expand:
            indent += self._indent_per_level
        else:
            indent += len(cls_name) + 1
        items = [(f.name, getattr(object, f.name)) for f in dataclass_fields(object) if f.repr]
        stream.write(self._format_block_start(cls_name + '(', indent))
        self._format_namespace_items(items, stream, indent, allowance, context, level)
        stream.write(self._format_block_end(')', indent - self._indent_per_level))

    _dispatch = {}

    def _pprint_dict(self, object, stream, indent, allowance, context, level):
        write = stream.write
        write(self._format_block_start('{', indent))
        self._write_indent_padding(write)
        length = len(object)
        if length:
            if self._sort_dicts:
                items = sorted(object.items(), key=_safe_tuple)
            else:
                items = object.items()
            self._format_dict_items(items, stream, indent, allowance + 1,
                                    context, level)
        write(self._format_block_end('}', indent))

    _dispatch[dict.__repr__] = _pprint_dict

    def _pprint_frozendict(self, object, stream, indent, allowance, context, level):
        write = stream.write
        cls = object.__class__
        if not len(object):
            write(repr(object))
            return

        write(self._format_block_start(cls.__name__ + "({", indent))
        self._write_indent_padding(write)

        if self._sort_dicts:
            items = sorted(object.items(), key=_safe_tuple)
        else:
            items = object.items()
        self._format_dict_items(
            items,
            stream,
            self._child_indent(indent, len(cls.__name__) + 1),
            allowance + 2,
            context,
            level,
        )
        write(self._format_block_end("})", indent))

    _dispatch[frozendict.__repr__] = _pprint_frozendict

    def _pprint_ordered_dict(self, object, stream, indent, allowance, context, level):
        if not len(object):
            stream.write(repr(object))
            return
        cls = object.__class__
        stream.write(cls.__name__ + '(')
        self._format_child(
            list(object.items()),
            stream,
            self._child_indent(indent, len(cls.__name__) + 1),
            allowance + 1,
            context,
            level,
            len(cls.__name__) + 1,
        )
        stream.write(')')

    _dispatch[_collections.OrderedDict.__repr__] = _pprint_ordered_dict

    def _pprint_dict_view(self, object, stream, indent, allowance, context, level):
        """Pretty print dict views (keys, values, items)."""
        if isinstance(object, self._dict_items_view):
            key = _safe_tuple
        else:
            key = _safe_key

        write = stream.write
        write(
            self._format_block_start(object.__class__.__name__ + "([", indent)
        )

        if len(object):
            if self._sort_dicts:
                entries = sorted(object, key=key)
            else:
                entries = object
            self._format_items(
                entries, stream, indent, allowance + 2, context, level
            )
        write(self._format_block_end("])", indent))

    def _pprint_mapping_abc_view(self, object, stream, indent, allowance, context, level):
        """Pretty print mapping views from collections.abc."""
        write = stream.write
        write(object.__class__.__name__ + '(')
        # Dispatch formatting to the view's _mapping
        self._format(object._mapping, stream, indent, allowance, context, level)
        write(')')

    _dict_keys_view = type({}.keys())
    _dispatch[_dict_keys_view.__repr__] = _pprint_dict_view

    _dict_values_view = type({}.values())
    _dispatch[_dict_values_view.__repr__] = _pprint_dict_view

    _dict_items_view = type({}.items())
    _dispatch[_dict_items_view.__repr__] = _pprint_dict_view

    _dispatch[_collections.abc.MappingView.__repr__] = _pprint_mapping_abc_view

    _view_reprs = {cls.__repr__ for cls in
                   (_dict_keys_view, _dict_values_view, _dict_items_view,
                    _collections.abc.MappingView)}

    def _pprint_list(self, object, stream, indent, allowance, context, level):
        stream.write(self._format_block_start('[', indent))
        self._format_items(object, stream, indent, allowance + 1,
                           context, level)
        stream.write(self._format_block_end(']', indent))

    _dispatch[list.__repr__] = _pprint_list

    def _pprint_tuple(self, object, stream, indent, allowance, context, level):
        stream.write(self._format_block_start('(', indent))
        if len(object) == 1 and not self._expand:
            endchar = ',)'
        else:
            endchar = ')'
        self._format_items(object, stream, indent, allowance + len(endchar),
                           context, level)
        stream.write(self._format_block_end(endchar, indent))

    _dispatch[tuple.__repr__] = _pprint_tuple

    def _pprint_set(self, object, stream, indent, allowance, context, level):
        if not len(object):
            stream.write(repr(object))
            return
        typ = object.__class__
        if typ is set:
            stream.write(self._format_block_start('{', indent))
            endchar = '}'
        else:
            stream.write(self._format_block_start(typ.__name__ + '({', indent))
            endchar = '})'
            if not self._expand:
                indent += len(typ.__name__) + 1
        object = sorted(object, key=_safe_key)
        self._format_items(object, stream, indent, allowance + len(endchar),
                           context, level)
        stream.write(self._format_block_end(endchar, indent))

    _dispatch[set.__repr__] = _pprint_set
    _dispatch[frozenset.__repr__] = _pprint_set

    def _pprint_str(self, object, stream, indent, allowance, context, level):
        write = stream.write
        if not len(object):
            write(repr(object))
            return
        chunks = []
        lines = object.splitlines(True)
        if level == 1:
            if self._expand:
                indent += self._indent_per_level
            else:
                indent += 1
            allowance += 1
        max_width1 = max_width = self._width - indent
        for i, line in enumerate(lines):
            rep = repr(line)
            if i == len(lines) - 1:
                max_width1 -= allowance
            if len(rep) <= max_width1:
                chunks.append(rep)
            else:
                # Lazy import to improve module import time
                import re

                # A list of alternating (non-space, space) strings
                parts = re.findall(r'\S*\s*', line)
                assert parts
                assert not parts[-1]
                parts.pop()  # drop empty last part
                max_width2 = max_width
                current = ''
                for j, part in enumerate(parts):
                    candidate = current + part
                    if j == len(parts) - 1 and i == len(lines) - 1:
                        max_width2 -= allowance
                    if len(repr(candidate)) > max_width2:
                        if current:
                            chunks.append(repr(current))
                        current = part
                    else:
                        current = candidate
                if current:
                    chunks.append(repr(current))
        if len(chunks) == 1:
            write(rep)
            return
        if level == 1:
            write(self._format_block_start("(", indent))
        for i, rep in enumerate(chunks):
            if i > 0:
                write('\n' + ' '*indent)
            write(rep)
        if level == 1:
            write(self._format_block_end(")", indent - self._indent_per_level))

    _dispatch[str.__repr__] = _pprint_str

    def _pprint_bytes(self, object, stream, indent, allowance, context, level):
        write = stream.write
        if len(object) <= 4:
            write(repr(object))
            return
        parens = level == 1
        if parens:
            if self._expand:
                indent += self._indent_per_level
            else:
                indent += 1
            allowance += 1
            write(self._format_block_start('(', indent))
        delim = ''
        for rep in _wrap_bytes_repr(object, self._width - indent, allowance):
            write(delim)
            write(rep)
            if not delim:
                delim = '\n' + ' '*indent
        if parens:
            write(self._format_block_end(')', indent - self._indent_per_level))

    _dispatch[bytes.__repr__] = _pprint_bytes

    def _pprint_bytearray(self, object, stream, indent, allowance, context, level):
        write = stream.write
        write(self._format_block_start('bytearray(', indent))
        if self._expand:
            write(' ' * self._indent_per_level)
            recursive_indent = indent + self._indent_per_level
        else:
            recursive_indent = indent + 10
        self._pprint_bytes(bytes(object), stream, recursive_indent,
                           allowance + 1, context, level + 1)
        write(self._format_block_end(')', indent))

    _dispatch[bytearray.__repr__] = _pprint_bytearray

    def _pprint_mappingproxy(self, object, stream, indent, allowance, context, level):
        stream.write('mappingproxy(')
        self._format_child(
            object.copy(),
            stream,
            self._child_indent(indent, 13),
            allowance + 1,
            context,
            level,
            13,
        )
        stream.write(')')

    _dispatch[_types.MappingProxyType.__repr__] = _pprint_mappingproxy

    def _pprint_simplenamespace(self, object, stream, indent, allowance, context, level):
        if type(object) is _types.SimpleNamespace:
            # The SimpleNamespace repr is "namespace" instead of the class
            # name, so we do the same here. For subclasses; use the class name.
            cls_name = 'namespace'
        else:
            cls_name = object.__class__.__name__
        if self._expand:
            indent += self._indent_per_level
        else:
            indent += len(cls_name) + 1
        items = object.__dict__.items()
        stream.write(self._format_block_start(cls_name + '(', indent))
        self._format_namespace_items(items, stream, indent, allowance, context,
                                     level)
        stream.write(self._format_block_end(')', indent - self._indent_per_level))

    _dispatch[_types.SimpleNamespace.__repr__] = _pprint_simplenamespace

    def _format_dict_items(self, items, stream, indent, allowance, context,
                           level):
        write = stream.write
        indent += self._indent_per_level
        delimnl = ',\n' + ' ' * indent
        last_index = len(items) - 1
        for i, (key, ent) in enumerate(items):
            last = i == last_index
            rep = self._repr(key, context, level)
            write(rep)
            write(': ')
            self._format_child(
                ent,
                stream,
                self._child_indent(indent, len(rep) + 2),
                allowance if last else 1,
                context,
                level,
                len(rep) + 2,
            )
            if not last:
                write(delimnl)
            elif self._expand:
                write(',')

    def _format_namespace_items(self, items, stream, indent, allowance, context, level):
        write = stream.write
        delimnl = ',\n' + ' ' * indent
        last_index = len(items) - 1
        for i, (key, ent) in enumerate(items):
            last = i == last_index
            write(key)
            write('=')
            if id(ent) in context:
                # Special-case representation of recursion to match standard
                # recursive dataclass repr.
                write("...")
            else:
                self._format_child(
                    ent,
                    stream,
                    self._child_indent(indent, len(key) + 1),
                    allowance if last else 1,
                    context,
                    level,
                    len(key) + 1,
                )
            if not last:
                write(delimnl)
            elif self._expand:
                write(',')

    def _format_items(self, items, stream, indent, allowance, context, level):
        write = stream.write
        indent += self._indent_per_level
        self._write_indent_padding(write)
        delimnl = ',\n' + ' ' * indent
        delim = ''
        width = max_width = self._width - indent + 1
        it = iter(items)
        try:
            next_ent = next(it)
        except StopIteration:
            return
        last = False
        while not last:
            ent = next_ent
            try:
                next_ent = next(it)
            except StopIteration:
                last = True
                max_width -= allowance
                width -= allowance
            if self._compact:
                rep = self._repr(ent, context, level)
                w = len(rep) + 2
                if width < w:
                    width = max_width
                    if delim:
                        delim = delimnl
                if width >= w:
                    width -= w
                    write(delim)
                    delim = ', '
                    write(rep)
                    continue
            write(delim)
            delim = delimnl
            self._format(ent, stream, indent,
                         allowance if last else 1,
                         context, level)
            if last and self._expand:
                write(',')

    def _repr(self, object, context, level):
        repr, readable, recursive = self.format(object, context.copy(),
                                                self._depth, level)
        if not readable:
            self._readable = False
        if recursive:
            self._recursive = True
        return repr

    def format(self, object, context, maxlevels, level):
        """Format object for a specific context, returning a string
        and flags indicating whether the representation is 'readable'
        and whether the object represents a recursive construct.
        """
        return self._safe_repr(object, context, maxlevels, level)

    def _pprint_default_dict(self, object, stream, indent, allowance, context, level):
        if not len(object):
            stream.write(repr(object))
            return
        rdf = self._repr(object.default_factory, context, level)
        cls = object.__class__
        if self._expand:
            stream.write('%s(%s, ' % (cls.__name__, rdf))
        else:
            indent += len(cls.__name__) + 1
            stream.write('%s(%s,\n%s' % (cls.__name__, rdf, ' ' * indent))
        self._pprint_dict(object, stream, indent, allowance + 1, context,
                          level)
        stream.write(')')

    _dispatch[_collections.defaultdict.__repr__] = _pprint_default_dict

    def _pprint_counter(self, object, stream, indent, allowance, context, level):
        if not len(object):
            stream.write(repr(object))
            return
        cls = object.__class__
        stream.write(self._format_block_start(cls.__name__ + '({', indent))
        self._write_indent_padding(stream.write)
        items = object.most_common()
        self._format_dict_items(
            items,
            stream,
            self._child_indent(indent, len(cls.__name__) + 1),
            allowance + 2,
            context,
            level,
        )
        stream.write(self._format_block_end('})', indent))

    _dispatch[_collections.Counter.__repr__] = _pprint_counter

    def _pprint_chain_map(self, object, stream, indent, allowance, context, level):
        if not len(object.maps):
            stream.write(repr(object))
            return
        cls = object.__class__
        stream.write(self._format_block_start(cls.__name__ + '(',
                                              indent + self._indent_per_level))
        if self._expand:
            indent += self._indent_per_level
        else:
            indent += len(cls.__name__) + 1
        for i, m in enumerate(object.maps):
            if i == len(object.maps) - 1:
                self._format(m, stream, indent, allowance + 1, context, level)
                if self._expand:
                    stream.write(',')
                stream.write(self._format_block_end(')', indent - self._indent_per_level))
            else:
                self._format(m, stream, indent, 1, context, level)
                stream.write(',\n' + ' ' * indent)

    _dispatch[_collections.ChainMap.__repr__] = _pprint_chain_map

    def _pprint_deque(self, object, stream, indent, allowance, context, level):
        if not len(object):
            stream.write(repr(object))
            return
        cls = object.__class__
        stream.write(self._format_block_start(cls.__name__ + '([', indent))
        if not self._expand:
            indent += len(cls.__name__) + 1
        if object.maxlen is None:
            self._format_items(object, stream, indent, allowance + 2,
                               context, level)
            stream.write(self._format_block_end('])', indent))
        else:
            self._format_items(object, stream, indent, 2,
                               context, level)
            rml = self._repr(object.maxlen, context, level)
            if self._expand:
                stream.write('%s], maxlen=%s)' % ('\n' + ' ' * indent, rml))
            else:
                stream.write('],\n%smaxlen=%s)' % (' ' * indent, rml))

    _dispatch[_collections.deque.__repr__] = _pprint_deque

    def _pprint_user_dict(self, object, stream, indent, allowance, context, level):
        self._format(object.data, stream, indent, allowance, context, level - 1)

    _dispatch[_collections.UserDict.__repr__] = _pprint_user_dict

    def _pprint_user_list(self, object, stream, indent, allowance, context, level):
        self._format(object.data, stream, indent, allowance, context, level - 1)

    _dispatch[_collections.UserList.__repr__] = _pprint_user_list

    def _pprint_user_string(self, object, stream, indent, allowance, context, level):
        self._format(object.data, stream, indent, allowance, context, level - 1)

    _dispatch[_collections.UserString.__repr__] = _pprint_user_string

    def _pprint_template(self, object, stream, indent, allowance, context, level):
        cls_name = object.__class__.__name__
        if self._expand:
            indent += self._indent_per_level
        else:
            indent += len(cls_name) + 1

        items = (
            ("strings", object.strings),
            ("interpolations", object.interpolations),
        )
        stream.write(self._format_block_start(cls_name + "(", indent))
        self._format_namespace_items(
            items, stream, indent, allowance, context, level
        )
        stream.write(
            self._format_block_end(")", indent - self._indent_per_level)
        )

    def _pprint_interpolation(self, object, stream, indent, allowance, context, level):
        cls_name = object.__class__.__name__
        if self._expand:
            indent += self._indent_per_level
            items = (
                ("value", object.value),
                ("expression", object.expression),
                ("conversion", object.conversion),
                ("format_spec", object.format_spec),
            )
            stream.write(self._format_block_start(cls_name + "(", indent))
            self._format_namespace_items(
                items, stream, indent, allowance, context, level
            )
            stream.write(
                self._format_block_end(")", indent - self._indent_per_level)
            )
        else:
            indent += len(cls_name)
            items = (
                object.value,
                object.expression,
                object.conversion,
                object.format_spec,
            )
            stream.write(cls_name + "(")
            self._format_items(
                items, stream, indent, allowance, context, level
            )
            stream.write(")")

    t = t"{0}"
    _dispatch[type(t).__repr__] = _pprint_template
    _dispatch[type(t.interpolations[0]).__repr__] = _pprint_interpolation
    del t

    def _safe_repr(self, object, context, maxlevels, level):
        # Return triple (repr_string, isreadable, isrecursive).
        typ = type(object)
        if typ in _builtin_scalars:
            return repr(object), True, False

        r = getattr(typ, "__repr__", None)

        if issubclass(typ, int) and r is int.__repr__:
            if self._underscore_numbers:
                return f"{object:_d}", True, False
            else:
                return repr(object), True, False

        if ((issubclass(typ, dict) and r is dict.__repr__)
            or (issubclass(typ, frozendict) and r is frozendict.__repr__)):
            is_frozendict = issubclass(typ, frozendict)
            if not object:
                if is_frozendict:
                    rep = f"{object.__class__.__name__}()"
                else:
                    rep = "{}"
                return rep, True, False
            objid = id(object)
            if maxlevels and level >= maxlevels:
                rep = "{...}"
                if is_frozendict:
                    rep = f"{object.__class__.__name__}({rep})"
                return rep, False, objid in context
            if objid in context:
                return _recursion(object), False, True
            context[objid] = 1
            readable = True
            recursive = False
            components = []
            append = components.append
            level += 1
            if self._sort_dicts:
                items = sorted(object.items(), key=_safe_tuple)
            else:
                items = object.items()
            for k, v in items:
                krepr, kreadable, krecur = self.format(
                    k, context, maxlevels, level)
                vrepr, vreadable, vrecur = self.format(
                    v, context, maxlevels, level)
                append("%s: %s" % (krepr, vrepr))
                readable = readable and kreadable and vreadable
                if krecur or vrecur:
                    recursive = True
            del context[objid]
            rep = "{%s}" % ", ".join(components)
            if is_frozendict:
                rep = f"{object.__class__.__name__}({rep})"
            return rep, readable, recursive

        if (issubclass(typ, list) and r is list.__repr__) or \
           (issubclass(typ, tuple) and r is tuple.__repr__):
            if issubclass(typ, list):
                if not object:
                    return "[]", True, False
                format = "[%s]"
            elif len(object) == 1:
                format = "(%s,)"
            else:
                if not object:
                    return "()", True, False
                format = "(%s)"
            objid = id(object)
            if maxlevels and level >= maxlevels:
                return format % "...", False, objid in context
            if objid in context:
                return _recursion(object), False, True
            context[objid] = 1
            readable = True
            recursive = False
            components = []
            append = components.append
            level += 1
            for o in object:
                orepr, oreadable, orecur = self.format(
                    o, context, maxlevels, level)
                append(orepr)
                if not oreadable:
                    readable = False
                if orecur:
                    recursive = True
            del context[objid]
            return format % ", ".join(components), readable, recursive

        if issubclass(typ, _collections.abc.MappingView) and r in self._view_reprs:
            objid = id(object)
            if maxlevels and level >= maxlevels:
                return "{...}", False, objid in context
            if objid in context:
                return _recursion(object), False, True
            key = _safe_key
            if issubclass(typ, (self._dict_items_view, _collections.abc.ItemsView)):
                key = _safe_tuple
            if hasattr(object, "_mapping"):
                # Dispatch formatting to the view's _mapping
                mapping_repr, readable, recursive = self.format(
                    object._mapping, context, maxlevels, level)
                return (typ.__name__ + '(%s)' % mapping_repr), readable, recursive
            elif hasattr(typ, "_mapping"):
                #  We have a view that somehow has lost its type's _mapping, raise
                #  an error by calling repr() instead of failing cryptically later
                return repr(object), True, False
            if self._sort_dicts:
                object = sorted(object, key=key)
            context[objid] = 1
            readable = True
            recursive = False
            components = []
            append = components.append
            level += 1
            for val in object:
                vrepr, vreadable, vrecur = self.format(
                    val, context, maxlevels, level)
                append(vrepr)
                readable = readable and vreadable
                if vrecur:
                    recursive = True
            del context[objid]
            return typ.__name__ + '([%s])' % ", ".join(components), readable, recursive

        rep = repr(object)
        return rep, (rep and not rep.startswith('<')), False


_builtin_scalars = frozenset({str, bytes, bytearray, float, complex,
                              bool, type(None)})


def _recursion(object):
    return ("<Recursion on %s with id=%s>"
            % (type(object).__name__, id(object)))


def _wrap_bytes_repr(object, width, allowance):
    current = b''
    last = len(object) // 4 * 4
    for i in range(0, len(object), 4):
        part = object[i: i+4]
        candidate = current + part
        if i == last:
            width -= allowance
        if len(repr(candidate)) > width:
            if current:
                yield repr(current)
            current = part
        else:
            current = candidate
    if current:
        yield repr(current)


# PEP 813 protocol definitions are initialized on demand so importing pprint
# alone keeps the traditional lightweight behavior.
def _load_protocol():
    if "Printer" in globals():
        return
    import enum
    from collections.abc import Iterable, Mapping, Set
    from dataclasses import dataclass
    from itertools import chain
    from _pprint import (
        VALUES, KWARGS, ITEMS, DELEGATE, Layout, BreakableString,
        BreakableBytes, FormattableNumber, _LeafMarker,
    )


    _EMPTY = ""
    _NL = "\n"
    _SPACE = " "
    _MISSING = sentinel("_MISSING")
    LEAF = sentinel("LEAF", repr="pprint.LEAF")
    type DescriptionType = Iterable[object]

    @dataclass(frozen=True)
    class Keyword:
        """A keyword item, printed as name=value."""

        name: str
        value: object
        default: object = _MISSING


    @dataclass(frozen=True)
    class Entry:
        """A key/value item, printed as key: value."""

        key: object
        value: object



    class _ComparisonError:
        """Stand in for a keyword value whose comparison to its default failed."""

        def __init__(self, error):
            self._error = error

        def __repr__(self):
            return f"<error comparing to default: {type(self._error).__name__}>"


    def _find_pprint(cls):
        """Return the __pprint__ method that applies to instances of cls, or None."""
        mro = cls.__mro__
        pprint_owner = next((base for base in mro if "__pprint__" in vars(base)), None)
        if pprint_owner is None:
            return None
        repr_owner = next(base for base in mro if "__repr__" in vars(base))
        if mro.index(pprint_owner) <= mro.index(repr_owner):
            return vars(pprint_owner)["__pprint__"]
        return None


    def _apply_default(keyword):
        """Hide a keyword if its value equals its declared default."""
        if keyword.default is _MISSING:
            return keyword
        try:
            same = bool(keyword.value == keyword.default)
        except Exception as error:
            return Keyword(keyword.name, _ComparisonError(error))
        return None if same else keyword


    def decompose(obj):
        """Read one level of an object's pretty-print description stream."""
        method = _find_pprint(type(obj))
        if method is None:
            return LEAF, None
        stream = iter(method(obj))

        first = next(stream, _MISSING)
        if first is DELEGATE:
            value = next(stream, _MISSING)
            return (DELEGATE, value) if value is not _MISSING else (LEAF, None)

        if isinstance(first, Layout):
            layout = first
        else:
            layout = Layout()
            if first is not _MISSING:
                stream = chain((first,), stream)

        items = []
        section = VALUES
        for item in stream:
            if item is VALUES or item is KWARGS or item is ITEMS:
                section = item
                continue

            match item:
                case tuple((str() as name, value)) if section is KWARGS:
                    item = Keyword(name, value)
                case tuple((str() as name, value, default)) if section is KWARGS:
                    item = Keyword(name, value, default)
                case tuple((key, value)) if section is ITEMS:
                    item = Entry(key, value)

            if isinstance(item, Keyword):
                item = _apply_default(item)
                if item is None:
                    continue
            items.append(item)

        name = type(obj).__name__ if layout.name is None else layout.name
        if layout.open is None:
            keyed = len(items) > 0 and all(isinstance(item, Entry) for item in items)
            if keyed:
                open_, close = f"{name}({{", "})"
            else:
                open_, close = f"{name}(", ")"
        else:
            open_ = layout.open
            close = _EMPTY if layout.close is None else layout.close

        if layout.close is not None:
            close = layout.close

        filled = Layout(
            hints=layout.hints,
            name=name,
            open=open_,
            close=close,
            sep=layout.sep,
            empty=open_ + close if layout.empty is None else layout.empty,
            single_close=close if layout.single_close is None else layout.single_close,
            recursion=layout.recursion,
            sortable=layout.sortable,
            hug=layout.hug,
        )
        return filled, items


    @dataclass(frozen=True)
    class _ValueDocument:
        value: object


    @dataclass(frozen=True)
    class _LazyDocument:
        value: object
        ancestors: tuple


    @dataclass(frozen=True)
    class _TextDocument:
        text: str
        source: object = None


    @dataclass(frozen=True)
    class _EntryDocument:
        key: object
        value: object
        key_source: object


    @dataclass(frozen=True)
    class _KeywordDocument:
        name: str
        value: object
        source: object


    @dataclass(frozen=True)
    class _ContainerDocument:
        source: object
        layout: Layout
        items: tuple


    def _build_document(obj, ancestors=()):
        """Build a printer-independent document node for *obj*.

        Nested objects' descriptions are read when layout conversion reaches them.
        """
        ancestor_ids = {id(ancestor) for ancestor in ancestors}

        header, items = decompose(obj)
        if header is LEAF:
            return _ValueDocument(obj)
        if header is DELEGATE:
            if id(obj) in ancestor_ids:
                return _TextDocument("...", obj)
            return _build_document(items, ancestors + (obj,))

        if id(obj) in ancestor_ids:
            return _TextDocument(header.recursion, obj)
        ancestors = ancestors + (obj,)
        documents = []
        for item in items:
            match item:
                case Entry(key=key, value=value):
                    documents.append(
                        _EntryDocument(
                            _LazyDocument(key, ancestors),
                            _LazyDocument(value, ancestors),
                            key,
                        )
                    )
                case Keyword(name=name, value=value):
                    documents.append(
                        _KeywordDocument(name, _LazyDocument(value, ancestors), item)
                    )
                case _:
                    documents.append(_LazyDocument(item, ancestors))
        return _ContainerDocument(obj, header, tuple(documents))

    # End of object descriptions and structural documents.
    ########################################################################


    ########################################################################
    # Printer formatting and rendering.
    #
    # A layout document is a tree of text and layout instructions. It represents
    # the output before line breaks are chosen; the renderer turns it into lines.
    @dataclass(frozen=True)
    class _Text:
        text: str


    @dataclass(frozen=True)
    class _Line:
        """Flat text when a group fits, or a line break otherwise."""

        flat: str = _SPACE


    @dataclass(frozen=True)
    class _Concat:
        parts: tuple


    @dataclass(frozen=True)
    class _Nest:
        width: int
        doc: object


    @dataclass(frozen=True)
    class _Align:
        doc: object


    @dataclass(frozen=True)
    class _Group:
        doc: object


    @dataclass(frozen=True)
    class _IfBroken:
        broken: str
        flat: str = _EMPTY


    @dataclass(frozen=True)
    class _KeyValue:
        key: object
        value: object
        hang: int | None


    class _Marker:
        """A marker rendered by a function from the printer's marker table."""

        __slots__ = ("value", "render", "top_level", "_flat")

        def __init__(self, value, render, top_level):
            self.value = value
            self.render = render
            self.top_level = top_level
            self._flat = None

        def lines(self, width, last_width):
            return list(self.render(
                self.value,
                width=width,
                last_width=last_width,
                top_level=self.top_level,
            ))

        def flat(self):
            if self._flat is None:
                self._flat = self.lines(_sys.maxsize, _sys.maxsize)
            return self._flat


    _SOFTLINE = _Line(_EMPTY)
    _COLON_SPACE = _Text(": ")


    def _join(separator, docs):
        parts = []
        for index, doc in enumerate(docs):
            if index:
                parts.append(separator)
            parts.append(doc)
        return _Concat(tuple(parts))


    class Expand(enum.Enum):
        """Policy for laying out containers that do not fit on one line."""

        NEVER = enum.auto()
        FIT = enum.auto()
        ALWAYS = enum.auto()

        def __repr__(self):
            return f"{type(self).__name__}.{self.name}"


    @dataclass(frozen=True)
    class _FormatOptions:
        indent: int
        width: int
        depth: int | None
        compact: bool
        sort_dicts: bool
        expand: Expand
        number_format: str | None
        markers: Mapping[type, object]


    class Printer:
        """Default printer. Calling an instance yields the formatted lines."""

        def __init__(
            self,
            indent=4,
            width=78,
            depth=None,
            *,
            compact=False,
            expand=Expand.FIT,
            sort_dicts=True,
            number_format=None,
        ):
            indent = int(indent)
            width = int(width)
            if indent < 0:
                raise ValueError('indent must be >= 0')
            if depth is not None and depth <= 0:
                raise ValueError('depth must be > 0')
            if not width:
                raise ValueError('width must be != 0')
            markers = {
                BreakableString: self._render_literal,
                BreakableBytes: self._render_literal,
                FormattableNumber: self._render_number,
            }
            self._options = _FormatOptions(
                indent, width, depth, compact, sort_dicts, expand, number_format,
                markers,
            )

        def __call__(self, obj):
            """Yield the formatted lines for *obj*."""
            # Build the complete structural document before applying printer settings.
            document = _build_document(obj)
            layout_document = _layout_document(document, 0, self._options)
            yield from _render_lines(layout_document, self._options.width)

        def _render_literal(self, marker, *, width, last_width, top_level):
            value = marker.value
            rep = repr(value)
            if len(rep) <= last_width or len(value) == 0:
                return [rep]
            allowance = width - last_width
            if top_level:
                pad = self._options.indent if self._options.expand is not Expand.NEVER else 1
                width -= pad
                allowance += 1
            else:
                pad = 0
            wrap = _wrap_bytes if isinstance(value, bytes) else _wrap_string
            chunks = wrap(value, width, allowance)
            if len(chunks) <= 1:
                return [rep]
            if not top_level:
                return chunks
            spaces = _SPACE * pad
            if self._options.expand is not Expand.NEVER:
                return ["(", *(spaces + chunk for chunk in chunks), ")"]
            return [
                "(" + chunks[0],
                *(spaces + chunk for chunk in chunks[1:-1]),
                spaces + chunks[-1] + ")",
            ]

        def _render_number(self, marker, *, width, last_width, top_level):
            number_format = self._options.number_format
            if number_format is None:
                return [repr(marker.value)]
            try:
                return [format(marker.value, number_format)]
            except Exception:
                return [repr(marker.value)]


    def _wrap_string(text, max_width, allowance):
        """Split a string's repr into chunks, as PrettyPrinter does."""
        import re

        chunks = []
        lines = text.splitlines(True)
        max_width1 = max_width
        for i, line in enumerate(lines):
            rep = repr(line)
            if i == len(lines) - 1:
                max_width1 -= allowance
            if len(rep) <= max_width1:
                chunks.append(rep)
                continue
            # A list of alternating (non-space, space) strings, ending with an
            # empty string.
            parts = re.findall(r"\S*\s*", line)
            parts.pop()
            max_width2 = max_width
            current = _EMPTY
            for j, part in enumerate(parts):
                candidate = current + part
                if j == len(parts) - 1 and i == len(lines) - 1:
                    max_width2 -= allowance
                if len(repr(candidate)) > max_width2:
                    if current:
                        chunks.append(repr(current))
                    current = part
                else:
                    current = candidate
            if current:
                chunks.append(repr(current))
        return chunks


    def _wrap_bytes(data, max_width, allowance):
        """Split a bytes value's repr into chunks, as PrettyPrinter does."""
        chunks = []
        current = b""
        last = len(data) // 4 * 4
        for i in range(0, len(data), 4):
            part = data[i:i + 4]
            candidate = current + part
            if i == last:
                max_width -= allowance
            if len(repr(candidate)) > max_width:
                if current:
                    chunks.append(repr(current))
                current = part
            else:
                current = candidate
        if current:
            chunks.append(repr(current))
        return chunks


    def _find_marker(value, markers):
        """Return the function in *markers* for *value*'s class, or None."""
        for cls in type(value).__mro__:
            render = markers.get(cls)
            if render is not None:
                return render
        return None


    def _layout_document(document, level, options):
        """Apply printer options to a structural document and return layout instructions."""
        match document:
            case _LazyDocument(value=value, ancestors=ancestors):
                return _layout_document(
                    _build_document(value, ancestors), level, options
                )
            case _TextDocument(text=text):
                return _Text(text)
            case _ValueDocument(value=value):
                render = _find_marker(value, options.markers)
                if render is None:
                    return _Text(repr(value))
                return _Marker(value, render, level == 0)
            case _ContainerDocument(layout=header, items=items):
                if not items:
                    return _Text(header.empty)
                if options.depth is not None and level >= options.depth:
                    return _Text(f"{header.open}...{header.close}")

                if header.sortable and options.sort_dicts:
                    items = _sorted_documents(items, level, options)
                hugged = None
                if header.hug and options.expand is not Expand.NEVER:
                    items = tuple(_resolve_item(item) for item in items)
                    hugged = _hugged_index(items)
                parts = [_item_document(item, level + 1, options) for item in items]
                if hugged is not None:
                    return _hugged_document(header, parts)
                positional = not any(
                    isinstance(item, (_EntryDocument, _KeywordDocument)) for item in items
                )
                return _container_document(header, parts, positional, level, options)
            case _:
                raise TypeError(f"unexpected document node: {document!r}")


    def _document_source(document):
        match document:
            case _ValueDocument(value=value):
                return value
            case _ContainerDocument(source=value):
                return value
            case _LazyDocument(value=value):
                return value
            case _EntryDocument(key_source=value):
                return value
            case _KeywordDocument(source=value):
                return value
            case _TextDocument(source=value):
                return value
            case _:
                raise TypeError(f"unexpected structural document: {document!r}")


    def _document_sort_key(item):
        """Return an entry's key, or the item itself, for sorting."""
        return item.key if isinstance(item, _EntryDocument) else item


    def _sorted_documents(items, level, options):
        """Sort an object's items, keeping keyword items after the others."""
        keywords = sorted(
            (item for item in items if isinstance(item, _KeywordDocument)),
            key=lambda item: item.name,
        )
        others = [item for item in items if not isinstance(item, _KeywordDocument)]
        return _sorted_values(others, level, options) + keywords


    def _sorted_values(items, level, options):
        if not any(
            isinstance(_document_source(_document_sort_key(item)), Set) for item in items
        ):
            try:
                return sorted(
                    items,
                    key=lambda item: _document_source(_document_sort_key(item)),
                )
            except TypeError:
                pass
        return sorted(
            items,
            key=lambda item: _flat_document(_document_sort_key(item), level + 1, options),
        )


    def _flat_document(document, level, options):
        layout_document = _layout_document(document, level, options)
        return _NL.join(_render_lines(_Group(layout_document), _sys.maxsize))


    def _item_document(item, level, options):
        match item:
            case _EntryDocument(key=key, value=value):
                hang = options.indent if options.expand is Expand.NEVER else None
                return _KeyValue(
                    _layout_document(key, level, options),
                    _layout_document(value, level, options),
                    hang,
                )
            case _KeywordDocument(name=name, value=value):
                return _Concat(
                    (_Text(f"{name}="), _layout_document(value, level, options))
                )
            case _:
                return _layout_document(item, level, options)


    def _resolve_item(item):
        """Build the documents of an item's lazy parts."""
        match item:
            case _LazyDocument(value=value, ancestors=ancestors):
                return _build_document(value, ancestors)
            case _KeywordDocument(value=_LazyDocument(value=value, ancestors=ancestors)):
                return _KeywordDocument(
                    item.name, _build_document(value, ancestors), item.source
                )
            case _:
                return item


    def _hugged_index(items):
        """Return the index of the only item that is a non-empty container, or None."""
        found = None
        for index, item in enumerate(items):
            document = item.value if isinstance(item, _KeywordDocument) else item
            if isinstance(document, _ContainerDocument) and len(document.items) > 0:
                if found is not None:
                    return None
                found = index
        return found


    def _hugged_document(header, parts):
        """Keep every item on the opening and closing lines.

        Only the one container among the items breaks across lines, so its
        brackets hug the object's own, as in ``defaultdict(<class 'list'>, {``.
        """
        close = header.single_close if len(parts) == 1 else header.close
        separator = _Text(header.sep + _SPACE)
        return _Group(
            _Concat((_Text(header.open), _join(separator, parts), _Text(close)))
        )


    def _container_document(header, parts, positional, level, options):
        close = header.single_close if len(parts) == 1 else header.close
        separator = _Text(header.sep)

        if options.expand is Expand.NEVER:
            if options.compact and positional:
                body = _join(_Concat((separator, _Group(_Line()))), parts)
                return _Concat((_Text(header.open), _Align(body), _Text(close)))
            body = _join(_Concat((separator, _Line())), parts)
            return _Group(_Concat((_Text(header.open), _Align(body), _Text(close))))

        body = _join(_Concat((separator, _Line())), parts)
        doc = _Concat(
            (
                _Text(header.open),
                _Nest(options.indent, _Concat((_SOFTLINE, body, _IfBroken(header.sep)))),
                _SOFTLINE,
                _IfBroken(header.close, flat=close),
            )
        )
        if options.expand is Expand.ALWAYS and level > 0:
            return doc
        return _Group(doc)


    def _render_lines(doc, width):
        out = []
        column = 0
        # Each pending item is (indent, flat, node): nodes come from the layout
        # document, while indent and flat carry the rendering context. Compound
        # nodes add their children to this stack as they are traversed. The stack
        # can grow to O(N), where N is the number of layout nodes: a deep document
        # leaves pending nodes at each level, while a wide _Concat adds many at once.
        stack = [(0, False, doc)]
        while stack:
            indent, flat, node = stack.pop()
            match node:
                case _Text(text=text):
                    parts = text.split(_NL)
                    for part in parts[:-1]:
                        out.append(part)
                        yield _EMPTY.join(out)
                        out.clear()
                    out.append(parts[-1])
                    column = len(parts[-1]) if len(parts) > 1 else column + len(text)
                case _Line(flat=flat_text):
                    if flat:
                        out.append(flat_text)
                        column += len(flat_text)
                    else:
                        yield _EMPTY.join(out)
                        out.clear()
                        out.append(_SPACE * indent)
                        column = indent
                case _Concat(parts=parts):
                    stack.extend((indent, flat, part) for part in reversed(parts))
                case _Nest(width=extra, doc=inner):
                    stack.append((indent + extra, flat, inner))
                case _Align(doc=inner):
                    stack.append((column, flat, inner))
                case _Group(doc=inner):
                    fits = flat or _fits(width - column, (indent, True, inner), stack)
                    stack.append((indent, fits, inner))
                case _IfBroken(broken=broken, flat=flat_text):
                    text = flat_text if flat else broken
                    out.append(text)
                    column += len(text)
                case _Marker():
                    if flat:
                        lines = node.flat()
                    else:
                        room = width - column
                        lines = node.lines(room, room - _trailing_width(stack))
                    start = column
                    for index, line in enumerate(lines):
                        if index > 0:
                            yield _EMPTY.join(out)
                            out.clear()
                            line = _SPACE * start + line
                            column = 0
                        out.append(line)
                        column += len(line)
                case _KeyValue(key=key, value=value, hang=hang):
                    if flat or hang is None:
                        stack.append((indent, flat, value))
                        stack.append((indent, flat, _COLON_SPACE))
                        stack.append((indent, flat, key))
                    elif isinstance(key, _Text) or _fits(
                        width - column, (indent, True, _Concat((key, _Text(":")))), []
                    ):
                        stack.append((indent, False, value))
                        stack.append((indent, False, _COLON_SPACE))
                        stack.append((indent, True, key))
                    else:
                        hanging = column + hang
                        stack.append((hanging, False, value))
                        stack.append((hanging, False, _Line()))
                        stack.append((indent, False, _Text(":")))
                        stack.append((indent, False, key))
        yield _EMPTY.join(out)


    def _fits(remaining, first, rest):
        local = [first]
        index = len(rest)
        while remaining >= 0:
            if local:
                indent, flat, node = local.pop()
            elif index:
                index -= 1
                indent, flat, node = rest[index]
            else:
                return True

            match node:
                case _Text(text=text):
                    remaining -= len(text)
                case _Line(flat=flat_text):
                    if flat:
                        remaining -= len(flat_text)
                    else:
                        return True
                case _Concat(parts=parts):
                    local.extend((indent, flat, part) for part in reversed(parts))
                case _Nest(doc=inner) | _Align(doc=inner) | _Group(doc=inner):
                    local.append((indent, flat, inner))
                case _IfBroken(broken=broken, flat=flat_text):
                    remaining -= len(flat_text if flat else broken)
                case _KeyValue(key=key, value=value):
                    local.append((indent, flat, _Concat((key, _COLON_SPACE, value))))
                case _Marker():
                    if flat:
                        lines = node.flat()
                        if len(lines) != 1:
                            return False
                    else:
                        lines = node.lines(remaining, remaining)
                    remaining -= len(lines[0])
                    if len(lines) > 1:
                        # The rest of the marker goes on later lines.
                        return remaining >= 0
        return False


    def _trailing_width(stack):
        """Return the width of the text that follows on the current line.

        The scan stops at the first possible line break, including any group,
        since whether a group breaks is not known yet.  This is the allowance
        that PrettyPrinter leaves for closing brackets and separators.
        """
        total = 0
        local = []
        index = len(stack)
        while True:
            if local:
                indent, flat, node = local.pop()
            elif index:
                index -= 1
                indent, flat, node = stack[index]
            else:
                return total

            match node:
                case _Text(text=text):
                    if _NL in text:
                        return total + text.index(_NL)
                    total += len(text)
                case _Line(flat=flat_text):
                    if not flat:
                        return total
                    total += len(flat_text)
                case _Concat(parts=parts):
                    local.extend((indent, flat, part) for part in reversed(parts))
                case _Nest(doc=inner) | _Align(doc=inner):
                    local.append((indent, flat, inner))
                case _IfBroken(broken=broken, flat=flat_text):
                    total += len(flat_text if flat else broken)
                case _:
                    return total

    # End of printer formatting and rendering.
    ########################################################################



    def _ordered_dict_pprint(obj):
        yield Layout(empty=f"{type(obj).__name__}()")
        yield ITEMS
        yield from obj.items()


    def _mapping_view_pprint(obj):
        yield Layout(open=f"{type(obj).__name__}(", close=")", hug=True)
        yield obj._mapping


    def _counter_pprint(obj):
        name = type(obj).__name__
        yield Layout(open=f"{name}({{", close="})", empty=f"{name}()")
        yield ITEMS
        yield from obj.most_common()


    def _chainmap_pprint(obj):
        yield Layout(open=f"{type(obj).__name__}(", close=")", empty=repr(obj))
        yield from obj.maps


    def _user_container_pprint(obj):
        yield DELEGATE
        yield obj.data
    globals().update(locals())
