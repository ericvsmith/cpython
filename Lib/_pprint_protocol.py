"""The pretty-print protocol of PEP 813.

The pprint module re-exports these names with lazy imports, so that importing
pprint alone does not pay for defining the printer.
"""

import dataclasses as _dataclass
import enum as _enum
import sys as _sys
from collections.abc import Iterable as _Iterable, Mapping as _Mapping, Set as _Set
from itertools import chain as _chain
lazy import re as _re

from _pprint import (
    VALUES, KWARGS, ITEMS, DELEGATE, Layout, BreakableString,
    BreakableBytes, FormattableNumber,
)


_EMPTY = ""
_NL = "\n"
_SPACE = " "
_MISSING = sentinel("_MISSING")
LEAF = sentinel("LEAF", repr="pprint.LEAF")
type DescriptionType = _Iterable[object]


@_dataclass.dataclass(frozen=True)
class Keyword:
    """A keyword item, printed as name=value."""

    name: str
    value: object
    default: object = _MISSING


@_dataclass.dataclass(frozen=True)
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
            stream = _chain((first,), stream)

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


@_dataclass.dataclass(frozen=True)
class _ValueDocument:
    value: object


@_dataclass.dataclass(frozen=True)
class _LazyDocument:
    value: object
    ancestors: tuple


@_dataclass.dataclass(frozen=True)
class _TextDocument:
    text: str
    source: object = None


@_dataclass.dataclass(frozen=True)
class _EntryDocument:
    key: object
    value: object
    key_source: object


@_dataclass.dataclass(frozen=True)
class _KeywordDocument:
    name: str
    value: object
    source: object


@_dataclass.dataclass(frozen=True)
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
@_dataclass.dataclass(frozen=True)
class _Text:
    text: str


@_dataclass.dataclass(frozen=True)
class _Line:
    """Flat text when a group fits, or a line break otherwise."""

    flat: str = _SPACE


@_dataclass.dataclass(frozen=True)
class _Concat:
    parts: tuple


@_dataclass.dataclass(frozen=True)
class _Nest:
    width: int
    doc: object


@_dataclass.dataclass(frozen=True)
class _Align:
    doc: object


@_dataclass.dataclass(frozen=True)
class _Group:
    doc: object


@_dataclass.dataclass(frozen=True)
class _IfBroken:
    broken: str
    flat: str = _EMPTY


@_dataclass.dataclass(frozen=True)
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


class Expand(_enum.Enum):
    """Policy for laying out containers that do not fit on one line."""

    NEVER = _enum.auto()
    FIT = _enum.auto()
    ALWAYS = _enum.auto()

    def __repr__(self):
        return f"{type(self).__name__}.{self.name}"


@_dataclass.dataclass(frozen=True)
class _FormatOptions:
    indent: int
    width: int
    depth: int | None
    compact: bool
    sort_dicts: bool
    expand: Expand
    number_format: str | None
    markers: _Mapping[type, object]


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
        parts = _re.findall(r"\S*\s*", line)
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
                return _hugged_document(header, parts, level, options)
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
        isinstance(_document_source(_document_sort_key(item)), _Set) for item in items
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


def _hugged_document(header, parts, level, options):
    """Keep every item on the opening and closing lines.

    Only the one container among the items breaks across lines, so its
    brackets hug the object's own, as in ``defaultdict(<class 'list'>, {``.
    """
    close = header.single_close if len(parts) == 1 else header.close
    separator = _Text(header.sep + _SPACE)
    doc = _Concat((_Text(header.open), _join(separator, parts), _Text(close)))
    if options.expand is Expand.ALWAYS and level > 0:
        return doc
    return _Group(doc)


def _compact_body(separator, parts, column, options):
    """Join items, packing those that fit on one line, as PrettyPrinter does.

    An item whose one-line form fits in the width left after *column* shares
    lines with its packable neighbors.  Any other item gets lines of its own,
    so a container that breaks never starts or ends partway along a line.
    """
    available = options.width - column
    packable = []
    for part in parts:
        lines = list(_render_lines(_Group(part), _sys.maxsize))
        packable.append(len(lines) == 1 and len(lines[0]) < available)
    docs = [parts[0]]
    for index in range(1, len(parts)):
        if packable[index - 1] and packable[index]:
            line = _Group(_Concat((_Line(), parts[index])))
        else:
            line = _Concat((_Line(), parts[index]))
        docs.append(_Concat((separator, line)))
    return _Concat(tuple(docs))


def _container_document(header, parts, positional, level, options):
    close = header.single_close if len(parts) == 1 else header.close
    separator = _Text(header.sep)
    compact = options.compact and positional

    if options.expand is Expand.NEVER:
        if compact:
            body = _compact_body(separator, parts, level + 1, options)
        else:
            body = _join(_Concat((separator, _Line())), parts)
        return _Group(_Concat((_Text(header.open), _Align(body), _Text(close))))

    if compact:
        body = _compact_body(separator, parts, options.indent * (level + 1), options)
    else:
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
