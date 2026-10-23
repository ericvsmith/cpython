"""Default implementation of the ``!p`` pretty-print conversion.

The module first builds a document from the object's structure and ``__pprint__``
description, independently of any Printer settings. A Printer then turns that
document into layout instructions using its formatting options, and the
renderer chooses line breaks to produce the output. Layout instructions are an
intermediate tree of text, indentation, grouping, and possible line breaks;
the renderer resolves them into output lines.

It also includes __pprint__ for built in types.
"""

import enum
import collections as _collections
import sys
import types as _types

from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass, field
from itertools import chain
from string.templatelib import Interpolation as _Interpolation
from string.templatelib import Template as _Template


_EMPTY = ""
_NL = "\n"
_SPACE = " "

VALUES = sentinel("VALUES", repr="pprint.VALUES")
KWARGS = sentinel("KWARGS", repr="pprint.KWARGS")
ITEMS = sentinel("ITEMS", repr="pprint.ITEMS")
DELEGATE = sentinel("DELEGATE", repr="pprint.DELEGATE")
LEAF = sentinel("LEAF", repr="pprint.LEAF")
_MISSING = sentinel("_MISSING")

type DescriptionType = Iterable[object]


########################################################################
# Object descriptions and structural documents.  Nothing in this section
# knows about a printer object.  It's purely driven by the objects data
# and what their __pprint__ methods return.

@dataclass(frozen=True, kw_only=True)
class Layout:
    """Describe an object's layout and carry printer-specific hints unchanged.

    The default printer ignores *hints*.
    """

    hints: Mapping[str, object] = field(
        default_factory=lambda: _types.MappingProxyType({})
    )
    name: str | None = None
    open: str | None = None
    close: str | None = None
    sep: str = ","
    empty: str | None = None
    single_close: str | None = None
    recursion: str = "..."
    sortable: bool = False
    hug: bool = False


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


class _LeafMarker:
    """Base class for markers, which must be leaves.

    A dataclass that generates __repr__() also generates __pprint__(), so the
    markers define __repr__() themselves.
    """

    __slots__ = ()

    def __repr__(self):
        return f"{type(self).__name__}({self.value!r})"


@dataclass(frozen=True, repr=False)
class BreakableString(_LeafMarker):
    """A string value that printers may split across output lines."""

    value: str


@dataclass(frozen=True, repr=False)
class BreakableBytes(_LeafMarker):
    """A bytes value that printers may split across output lines."""

    value: bytes


@dataclass(frozen=True, repr=False)
class FormattableNumber(_LeafMarker):
    """A number that printers may format according to their settings."""

    value: object


_BUILTIN_MARKERS = frozenset({BreakableString, BreakableBytes, FormattableNumber})


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

    # A marker, such as a BreakableString, has no __pprint__(), so it is a
    # leaf here.  Which markers are rendered specially is up to the printer.
    # Every str, bytes, int and float delegates to one of the built-in
    # markers, so skip decompose() for those.
    if type(obj) in _BUILTIN_MARKERS:
        return _ValueDocument(obj)
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
    """A marker that a function from the printer's marker table renders.

    The function returns the marker's lines, which can depend on the column
    where the marker starts.  That is only known while rendering.
    """

    __slots__ = ("value", "render", "top_level", "_flat")

    def __init__(self, value, render, top_level):
        self.value = value
        self.render = render
        self.top_level = top_level
        self._flat = None

    def lines(self, width, last_width):
        return list(
            self.render(
                self.value,
                width=width,
                last_width=last_width,
                top_level=self.top_level,
            )
        )

    def flat(self):
        """Return the lines for unlimited width, normally just one."""
        if self._flat is None:
            self._flat = self.lines(sys.maxsize, sys.maxsize)
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
    """Default printer. Calling an instance yields the formatted lines.

    Markers, such as BreakableString, are rendered by the functions in the
    printer's marker table, which maps a marker class to its function.  A
    function is called as ``render(marker, *, width, last_width, top_level)``
    and returns an iterable of lines.  *width* is the room for each line,
    from the column where the marker starts, and *last_width* is the room for
    the last line, which leaves space for any text that follows it.  The
    printer places the first line at the current position and the rest at
    the marker's starting column, so a line can start with extra spaces to
    indent it further.  *top_level* is true when the marker is the whole
    object being printed.  With unlimited width, a function returns the
    marker's one-line form.  A marker that is not in the table is printed
    with repr().
    """

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
        markers = {
            BreakableString: self._render_literal,
            BreakableBytes: self._render_literal,
            FormattableNumber: self._render_number,
        }
        self._options = _FormatOptions(
            indent, width, depth, compact, sort_dicts, expand, number_format, markers
        )

    def __call__(self, obj):
        """Yield the formatted lines for *obj*."""
        # Build the complete structural document before applying printer settings.
        document = _build_document(obj)
        layout_document = _layout_document(document, 0, self._options)
        yield from _render_lines(layout_document, self._options.width)

    def _render_literal(self, marker, *, width, last_width, top_level):
        """Split a str or bytes value into literals, as PrettyPrinter does."""
        value = marker.value
        rep = repr(value)
        if len(rep) <= last_width or len(value) == 0:
            return [rep]

        allowance = width - last_width
        if top_level:
            # The literal is the whole object, so it is parenthesized.
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
        """Format a number with the number_format option."""
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
    return _NL.join(_render_lines(_Group(layout_document), sys.maxsize))


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

########################################################################
# __pprint__ implementations for built-in and internal types.

def _list_pprint(obj):
    yield Layout(open="[", close="]", recursion="[...]")
    yield from obj


def _dict_pprint(obj):
    yield Layout(open="{", close="}", recursion="{...}", sortable=True)
    yield ITEMS
    yield from obj.items()


def _frozendict_pprint(obj):
    name = type(obj).__name__
    yield Layout(
        open=f"{name}({{", close="})", empty=f"{name}()", sortable=True
    )
    yield ITEMS
    yield from obj.items()


def _ordered_dict_pprint(obj):
    yield Layout(empty=f"{type(obj).__name__}()")
    yield ITEMS
    yield from obj.items()


def _dict_view_pprint(obj):
    name = type(obj).__name__
    yield Layout(open=f"{name}([", close="])", sortable=True)
    yield from obj


def _mapping_view_pprint(obj):
    yield Layout(open=f"{type(obj).__name__}(", close=")", hug=True)
    yield obj._mapping


def _tuple_pprint(obj):
    yield Layout(open="(", close=")", single_close=",)", recursion="(...)")
    yield from obj


def _set_pprint(obj):
    if type(obj) is set:
        yield Layout(open="{", close="}", empty="set()", sortable=True)
    else:
        name = type(obj).__name__
        yield Layout(
            open=f"{name}({{", close="})", empty=f"{name}()", sortable=True
        )
    yield from obj


def _frozen_set_pprint(obj):
    name = type(obj).__name__
    yield Layout(
        open=f"{name}({{", close="})", empty=f"{name}()", sortable=True
    )
    yield from obj


def _str_pprint(obj):
    yield DELEGATE
    yield BreakableString(obj)


def _bytes_pprint(obj):
    yield DELEGATE
    yield BreakableBytes(obj)


def _int_pprint(obj):
    yield DELEGATE
    yield FormattableNumber(obj)


def _float_pprint(obj):
    yield DELEGATE
    yield FormattableNumber(obj)


def _bytearray_pprint(obj):
    # There is only one item, so an empty separator leaves out the trailing
    # comma when it breaks.
    yield Layout(open="bytearray(", close=")", sep=_EMPTY)
    yield bytes(obj)


def _mappingproxy_pprint(obj):
    yield Layout(open="mappingproxy(", close=")", hug=True)
    yield dict(obj)


def _namespace_pprint(obj):
    name = "namespace" if type(obj) is _types.SimpleNamespace else type(obj).__name__
    yield Layout(open=f"{name}(", close=")")
    yield KWARGS
    yield from obj.__dict__.items()


def _defaultdict_pprint(obj):
    yield Layout(open=f"{type(obj).__name__}(", close=")", hug=True)
    yield obj.default_factory
    yield dict(obj)


def _counter_pprint(obj):
    name = type(obj).__name__
    yield Layout(open=f"{name}({{", close="})", empty=f"{name}()")
    yield ITEMS
    yield from obj.most_common()


def _chainmap_pprint(obj):
    yield Layout(open=f"{type(obj).__name__}(", close=")", empty=repr(obj))
    yield from obj.maps


def _deque_pprint(obj):
    yield Layout(recursion="[...]", hug=True)
    yield list(obj)
    if obj.maxlen is not None:
        yield KWARGS
        yield "maxlen", obj.maxlen


def _user_container_pprint(obj):
    yield DELEGATE
    yield obj.data


def _template_pprint(obj):
    name = type(obj).__name__
    yield Layout(open=f"{name}(", close=")")
    yield KWARGS
    yield "strings", obj.strings
    yield "interpolations", obj.interpolations


def _interpolation_pprint(obj):
    # Positional, to agree with repr().
    yield Layout(open=f"{type(obj).__name__}(", close=")")
    yield obj.value
    yield obj.expression
    yield obj.conversion
    yield obj.format_spec
    if obj.printer is not None:
        yield KWARGS
        yield "printer", obj.printer


# End of __pprint__ implementations.
########################################################################

