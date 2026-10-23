import _pprint
import collections
import enum
import pprint
import types
import unittest
from dataclasses import dataclass
from string.templatelib import Interpolation
from typing import NamedTuple

from pprint import (
    DELEGATE,
    KWARGS,
    LEAF,
    BreakableBytes,
    BreakableString,
    Expand,
    FormattableNumber,
    Layout,
    Printer,
    decompose,
)


def pformat(obj, **options):
    return "\n".join(Printer(**options)(obj))


class PprintProtocolTests(unittest.TestCase):
    def test_sort_keywords_by_name(self):
        class Example:
            def __pprint__(self):
                yield Layout(sortable=True)
                yield KWARGS
                yield "b", 1
                yield "a", 10
                yield "c", None

        self.assertEqual(pformat(Example()), "Example(a=10, b=1, c=None)")
        self.assertEqual(
            pformat(Example(), sort_dicts=False),
            "Example(b=1, a=10, c=None)",
        )

    def test_sort_keywords_after_other_items(self):
        class Example:
            def __pprint__(self):
                yield Layout(sortable=True)
                yield pprint.Keyword("b", 0)
                yield "z"
                yield pprint.Keyword("a", 10)
                yield "y"

        self.assertEqual(pformat(Example()), "Example('y', 'z', a=10, b=0)")

    def test_invalid_printer_options(self):
        for options in ({"indent": -1}, {"width": 0}, {"depth": 0}, {"depth": -1}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    Printer(**options)

    def test_printer_normalizes_width_and_indent(self):
        self.assertEqual(
            pformat([1, 2], width="5", indent="2"),
            "[\n  1,\n  2,\n]",
        )

    def test_close_without_open(self):
        class Custom:
            def __pprint__(self):
                yield Layout(close="]")
                yield 1

        layout, items = decompose(Custom())
        self.assertEqual(layout.open, "Custom(")
        self.assertEqual(layout.close, "]")
        self.assertEqual(layout.empty, "Custom(]")
        self.assertEqual(layout.single_close, "]")
        self.assertEqual(items, [1])
        self.assertEqual(pformat(Custom()), "Custom(1]")

    def test_namedtuple_descriptions(self):
        Point = collections.namedtuple("Point", "x y")

        class TypedPoint(NamedTuple):
            x: int
            y: int

        points = (
            (Point(1, 2), "Point(x=1, y=2)"),
            (TypedPoint(1, 2), "TypedPoint(x=1, y=2)"),
        )
        for point, expected in points:
            with self.subTest(type=type(point).__name__):
                self.assertEqual("\n".join(Printer()(point)), expected)

    def test_builtin_and_collection_descriptions(self):
        class View(collections.abc.MappingView):
            __slots__ = ()

        template = t"{1}"
        objects = [
            {},
            [],
            frozendict({1: 2}),
            collections.OrderedDict(a=1),
            {1: 2}.keys(),
            {1: 2}.values(),
            {1: 2}.items(),
            View({1: 2}),
            (1, 2),
            {1, 2},
            frozenset({1, 2}),
            "a long string that can wrap across lines when pretty printed",
            b"some bytes",
            bytearray(b"some bytes"),
            types.MappingProxyType({1: 2}),
            types.SimpleNamespace(a=1),
            collections.defaultdict(list, {1: 2}),
            collections.Counter("aba"),
            collections.ChainMap({1: 2}),
            collections.deque([1, 2], maxlen=3),
            collections.UserDict({1: 2}),
            collections.UserList([1, 2]),
            collections.UserString("text"),
            template,
            template.interpolations[0],
        ]

        for obj in objects:
            with self.subTest(type=type(obj).__name__):
                self.assertTrue(callable(getattr(type(obj), "__pprint__", None)))
                self.assertIsNotNone(decompose(obj)[0])
                self.assertIsInstance("\n".join(Printer()(obj)), str)

    def test_string_and_bytes_wrap(self):
        text = "one two three four five six seven eight nine ten eleven twelve"
        self.assertIn("\n", "\n".join(Printer(width=20)(text)))
        # Like PrettyPrinter, only a bytes value that is split is parenthesized.
        self.assertEqual("\n".join(Printer()(b"some bytes")), "b'some bytes'")

    def test_printer_call_yields_lines(self):
        printer = Printer(width=20)
        obj = {"first": [1, 2, 3], "second": [4, 5, 6]}
        lines = printer(obj)
        self.assertEqual("\n".join(lines), "\n".join(printer(obj)))

    def test_layout_hints(self):
        default_hints = Layout().hints
        self.assertEqual(default_hints, {})
        with self.assertRaises(TypeError):
            default_hints["html.role"] = "table"

        hints = {"html.role": "table"}

        @dataclass
        class Table:
            headers: list[str]
            rows: list[list[object]]

            def __pprint__(self):
                yield Layout(hints=hints)
                yield KWARGS
                yield "headers", self.headers
                yield "rows", self.rows

        table = Table(["Bass", "Strings"], [["Precision", 4], ["Stingray", 5]])
        layout, _ = decompose(table)
        self.assertIs(layout.hints, hints)
        self.assertEqual(
            "\n".join(Printer()(table)),
            "Table(headers=['Bass', 'Strings'], rows=[['Precision', 4], ['Stingray', 5]])",
        )


class LeafTests(unittest.TestCase):
    def test_leaf(self):
        self.assertEqual(decompose(object()), (LEAF, None))
        self.assertEqual(repr(LEAF), "pprint.LEAF")

    def test_delegate_without_value_is_a_leaf(self):
        class OnlyDelegate:
            def __pprint__(self):
                yield DELEGATE

            def __repr__(self):
                return "OnlyDelegate()"

        self.assertEqual(decompose(OnlyDelegate()), (LEAF, None))
        self.assertEqual(pformat(OnlyDelegate()), "OnlyDelegate()")

    def test_empty_container_is_not_a_leaf(self):
        layout, items = decompose([])
        self.assertIsInstance(layout, Layout)
        self.assertEqual(items, [])


class PublicNamesTests(unittest.TestCase):
    def test_reexported_from_pprint(self):
        c_names = (
            "VALUES", "KWARGS", "ITEMS", "DELEGATE", "Layout",
            "BreakableString", "BreakableBytes", "FormattableNumber",
        )
        for name in c_names:
            with self.subTest(name=name):
                self.assertIn(name, pprint.__all__)
                self.assertIs(getattr(pprint, name), getattr(_pprint, name))

    def test_description_type(self):
        def method(self) -> pprint.DescriptionType:
            yield 1

        self.assertIs(method.__annotations__["return"], pprint.DescriptionType)


class NumberTests(unittest.TestCase):
    def test_int_and_float_delegate(self):
        self.assertEqual(decompose(1), (DELEGATE, FormattableNumber(1)))
        self.assertEqual(decompose(1.5), (DELEGATE, FormattableNumber(1.5)))

    def test_default_is_repr(self):
        self.assertEqual(pformat([10**9, 1234567.125]), "[1000000000, 1234567.125]")

    def test_number_format(self):
        self.assertEqual(
            pformat([10**9, 1234567.125], number_format="_"),
            "[1_000_000_000, 1_234_567.125]",
        )
        self.assertEqual(
            pformat([10**9, 1234567.125], number_format=","),
            "[1,000,000,000, 1,234,567.125]",
        )

    def test_number_format_error_uses_repr(self):
        # 'x' is valid for an int, but not for a float.
        self.assertEqual(pformat([255, 1.5], number_format="x"), "[ff, 1.5]")
        self.assertEqual(pformat(FormattableNumber("text"), number_format=","), "'text'")

    def test_subclasses_that_override_repr_are_leaves(self):
        class Color(enum.IntEnum):
            RED = 1000

        self.assertEqual(decompose(True), (LEAF, None))
        self.assertEqual(decompose(Color.RED), (LEAF, None))
        self.assertEqual(
            pformat([True, Color.RED], number_format=","),
            "[True, <Color.RED: 1000>]",
        )

    def test_plain_subclass_is_formatted(self):
        class MyInt(int):
            pass

        self.assertEqual(pformat(MyInt(1000), number_format=","), "1,000")


class LiteralTests(unittest.TestCase):
    TEXT = "word " * 12
    DATA = b"0123456789" * 6

    def test_short_literals(self):
        self.assertEqual(pformat("abc"), "'abc'")
        self.assertEqual(pformat(b"some bytes"), "b'some bytes'")
        self.assertEqual(pformat(bytearray(b"ab")), "bytearray(b'ab')")

    def test_top_level_string(self):
        self.assertEqual(
            pformat(self.TEXT, width=40, indent=1, expand=Expand.NEVER),
            "('word word word word word word word '\n"
            " 'word word word word word ')",
        )
        self.assertEqual(
            pformat(self.TEXT, width=40),
            "(\n"
            "    'word word word word word word '\n"
            "    'word word word word word word '\n"
            ")",
        )

    def test_string_in_container_is_not_parenthesized(self):
        self.assertEqual(
            pformat([self.TEXT, 1], width=40, indent=1, expand=Expand.NEVER),
            "['word word word word word word word '\n"
            " 'word word word word word ',\n"
            " 1]",
        )
        self.assertEqual(
            pformat([self.TEXT, 1], width=40),
            "[\n"
            "    'word word word word word word '\n"
            "    'word word word word word word ',\n"
            "    1,\n"
            "]",
        )

    def test_dict_value_continuation_is_aligned(self):
        self.assertEqual(
            pformat({"key": self.TEXT}, width=40),
            "{\n"
            "    'key': 'word word word word word '\n"
            "           'word word word word word '\n"
            "           'word word ',\n"
            "}",
        )

    def test_matches_pretty_printer(self):
        for obj in (self.TEXT, [self.TEXT, 1], {"k": [self.TEXT]}, self.DATA, [self.DATA]):
            with self.subTest(obj=obj):
                self.assertEqual(
                    pformat(obj, width=40, indent=1, expand=Expand.NEVER),
                    pprint.pformat(obj, width=40),
                )
                self.assertEqual(
                    pformat(obj, width=40),
                    pprint.pformat(obj, width=40, indent=4, expand=True),
                )

    def test_bytearray(self):
        data = bytearray(b"0123456789" * 8)
        self.assertEqual(
            pformat(data, width=40, indent=1, expand=Expand.NEVER),
            pprint.pformat(data, width=40),
        )
        self.assertEqual(
            pformat(data, width=40),
            "bytearray(\n"
            "    b'01234567890123456789012345678901'\n"
            "    b'23456789012345678901234567890123'\n"
            "    b'4567890123456789'\n"
            ")",
        )

    def test_breakable_string_from_user_class(self):
        class Text:
            def __init__(self, text):
                self.text = text

            def __pprint__(self):
                yield DELEGATE
                yield BreakableString(self.text)

        self.assertEqual(pformat(Text(self.TEXT), width=40), pformat(self.TEXT, width=40))


class MarkerTableTests(unittest.TestCase):
    # The marker table isn't public yet, so these tests add entries to the
    # private one, as a future public option would.

    def test_markers_are_leaves(self):
        for marker in (BreakableString("a"), BreakableBytes(b"a"), FormattableNumber(1)):
            with self.subTest(marker=marker):
                self.assertEqual(decompose(marker), (LEAF, None))
                self.assertFalse(hasattr(marker, "__pprint__"))
        self.assertEqual(repr(BreakableString("a")), "BreakableString('a')")

    def test_default_markers(self):
        self.assertEqual(
            set(Printer()._options.markers),
            {BreakableString, BreakableBytes, FormattableNumber},
        )

    def test_marker_without_an_entry_is_printed_with_repr(self):
        printer = Printer()
        del printer._options.markers[FormattableNumber]
        self.assertEqual("\n".join(printer(FormattableNumber(1))), "FormattableNumber(1)")

    def test_new_marker(self):
        @dataclass(frozen=True, repr=False)
        class Shout(_pprint._LeafMarker):
            value: str

        def render_shout(marker, *, width, last_width, top_level):
            yield marker.value.upper()

        class Note:
            def __pprint__(self):
                yield KWARGS
                yield "lyric", Shout("all about that bass")

        printer = Printer()
        printer._options.markers[Shout] = render_shout
        self.assertEqual("\n".join(printer(Note())), "Note(lyric=ALL ABOUT THAT BASS)")
        # A printer without the entry prints the marker with repr().
        self.assertEqual(pformat(Note()), "Note(lyric=Shout('all about that bass'))")

    def test_marker_lines_start_at_its_column(self):
        @dataclass(frozen=True, repr=False)
        class Verse(_pprint._LeafMarker):
            value: tuple

        def render_verse(marker, *, width, last_width, top_level):
            text = " / ".join(marker.value)
            if len(text) <= last_width:
                return [text]
            return list(marker.value)

        printer = Printer(width=30)
        printer._options.markers[Verse] = render_verse
        verse = Verse(("all about that bass", "no treble"))
        self.assertEqual(
            "\n".join(printer({"verse": verse})),
            "{\n"
            "    'verse': all about that bass\n"
            "             no treble,\n"
            "}",
        )
        self.assertEqual(
            "\n".join(Printer(width=78)({"verse": verse})),
            "{'verse': Verse(('all about that bass', 'no treble'))}",
        )

    def test_marker_subclass(self):
        class Loud(BreakableString):
            pass

        self.assertEqual(pformat(Loud("abc")), "'abc'")

    def test_replace_a_default_marker(self):
        def render_number(marker, *, width, last_width, top_level):
            yield f"<{marker.value}>"

        printer = Printer()
        printer._options.markers[FormattableNumber] = render_number
        self.assertEqual("\n".join(printer([1, 2.5])), "[<1>, <2.5>]")


class HugTests(unittest.TestCase):
    WORDS = ["precision", "jazz", "stingray", "thunderbird", "rickenbacker"]

    def test_defaultdict(self):
        obj = collections.defaultdict(list, {w: [1] for w in self.WORDS[:3]})
        self.assertEqual(
            pformat(obj, width=40),
            "defaultdict(<class 'list'>, {\n"
            "    'jazz': [1],\n"
            "    'precision': [1],\n"
            "    'stingray': [1],\n"
            "})",
        )
        self.assertEqual(
            pformat(obj, width=40, indent=1, expand=Expand.NEVER),
            pprint.pformat(obj, width=40),
        )

    def test_matches_pretty_printer(self):
        mapping = {w: len(w) for w in self.WORDS}
        objects = [
            collections.defaultdict(list, {w: [1] for w in self.WORDS}),
            types.MappingProxyType(mapping),
            collections.abc.KeysView(mapping),
            collections.deque(self.WORDS),
            collections.deque(self.WORDS, maxlen=10),
        ]
        for obj in objects:
            with self.subTest(type=type(obj).__name__):
                self.assertEqual(
                    pformat(obj, width=40),
                    pprint.pformat(obj, width=40, indent=4, expand=True),
                )

    def test_deque_maxlen_never(self):
        obj = collections.deque(self.WORDS, maxlen=10)
        self.assertEqual(
            pformat(obj, width=40, indent=1, expand=Expand.NEVER),
            pprint.pformat(obj, width=40),
        )

    def test_fits_on_one_line(self):
        obj = collections.deque([1, 2], maxlen=3)
        self.assertEqual(pformat(obj), repr(obj))

    def test_no_hug_with_two_containers(self):
        class Pair:
            def __pprint__(self):
                yield Layout(hug=True)
                yield ["precision", "jazz"]
                yield ["stingray", "thunderbird"]

        self.assertEqual(
            pformat(Pair(), width=40),
            "Pair(\n"
            "    ['precision', 'jazz'],\n"
            "    ['stingray', 'thunderbird'],\n"
            ")",
        )

    def test_hug_ignored_when_never(self):
        obj = collections.defaultdict(list, {w: [1] for w in self.WORDS})
        self.assertTrue(pformat(obj, width=40, expand=Expand.NEVER).startswith(
            "defaultdict(<class 'list'>,\n"
        ))


class DescriptionTests(unittest.TestCase):
    def test_ordered_dict(self):
        obj = collections.OrderedDict(b=2, a=1)
        self.assertEqual(pformat(obj), repr(obj))
        self.assertEqual(
            pformat(obj, width=10),
            "OrderedDict({\n"
            "    'b': 2,\n"
            "    'a': 1,\n"
            "})",
        )

    def test_tuple_recursion(self):
        items = []
        obj = (items,)
        items.append(obj)
        self.assertEqual(pformat(obj), repr(obj))

    def test_deque_recursion(self):
        obj = collections.deque()
        obj.append(obj)
        self.assertEqual(pformat(obj), repr(obj))

    def test_interpolation_agrees_with_repr(self):
        value = Interpolation([1, 2], "x", "r", "")
        self.assertEqual(pformat(value), repr(value))


if __name__ == "__main__":
    unittest.main()
