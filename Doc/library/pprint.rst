:mod:`!pprint` --- Data pretty printer
======================================

.. module:: pprint
   :synopsis: Data pretty printer.

**Source code:** :source:`Lib/pprint.py`

--------------

The :mod:`!pprint` module provides a capability to "pretty-print" arbitrary
Python data structures in a form which can be used as input to the interpreter.
If the formatted structures include objects which are not fundamental Python
types, the representation may not be loadable.  This may be the case if objects
such as files, sockets or classes are included, as well as many other
objects which are not representable as Python literals.

The formatted representation keeps objects on a single line if it can, and
breaks them onto multiple lines if they don't fit within the allowed width,
adjustable by the *width* parameter defaulting to 80 characters.

Classes can describe how their instances are pretty printed with a
:meth:`~object.__pprint__` method, and the :class:`Printer` class lays out
those descriptions.  See :ref:`pprint-protocol` for details.

.. versionchanged:: 3.9
   Added support for pretty-printing :class:`types.SimpleNamespace`.

.. versionchanged:: 3.10
   Added support for pretty-printing :class:`dataclasses.dataclass`.

.. _pprint-functions:

Functions
---------

.. function:: pp(object, stream=None, indent=1, width=80, depth=None, *, \
                 compact=False, expand=False, sort_dicts=False, \
                 underscore_numbers=False)

   Prints the formatted representation of *object*, followed by a newline.
   This function may be used in the interactive interpreter
   instead of the :func:`print` function for inspecting values.
   Tip: you can reassign ``print = pprint.pp`` for use within a scope.

   :param object:
      The object to be printed.

   :param stream:
      A file-like object to which the output will be written
      by calling its :meth:`!write` method.
      If ``None`` (the default), :data:`sys.stdout` is used.
   :type stream: :term:`file-like object` | None

   :param int indent:
      The amount of indentation added for each nesting level.

   :param int width:
      The desired maximum number of characters per line in the output.
      If a structure cannot be formatted within the width constraint,
      a best effort will be made.

   :param depth:
      The number of nesting levels which may be printed.
      If the data structure being printed is too deep,
      the next contained level is replaced by ``...``.
      If ``None`` (the default), there is no constraint
      on the depth of the objects being formatted.
   :type depth: int | None

   :param bool compact:
      Control the way long :term:`sequences <sequence>` are formatted.
      If ``False`` (the default),
      each item of a sequence will be formatted on a separate line,
      otherwise as many items as will fit within the *width*
      will be formatted on each output line.
      Incompatible with *expand*.

   :param bool expand:
      If ``True``,
      opening parentheses and brackets will be followed by a newline and the
      following content will be indented by one level, similar to
      pretty-printed JSON. Incompatible with *compact*.

   :param bool sort_dicts:
      If ``True``, dictionaries will be formatted with
      their keys sorted, otherwise
      they will be displayed in insertion order (the default).

   :param bool underscore_numbers:
      If ``True``,
      integers will be formatted with the ``_`` character for a thousands separator,
      otherwise underscores are not displayed (the default).

   >>> import pprint
   >>> stuff = ['spam', 'eggs', 'lumberjack', 'knights', 'ni']
   >>> stuff.insert(0, stuff)
   >>> pprint.pp(stuff)
   [<Recursion on list with id=...>,
    'spam',
    'eggs',
    'lumberjack',
    'knights',
    'ni']

   .. versionadded:: 3.8


.. function:: pprint(object, stream=None, indent=1, width=80, depth=None, *, \
                     compact=False, expand=False, sort_dicts=True, \
                     underscore_numbers=False)

   Alias for :func:`~pprint.pp` with *sort_dicts* set to ``True`` by default,
   which would automatically sort the dictionaries' keys,
   you might want to use :func:`~pprint.pp` instead where it is ``False`` by default.


.. function:: pformat(object, indent=1, width=80, depth=None, *, \
                      compact=False, expand=False, sort_dicts=True, \
                      underscore_numbers=False)

   Return the formatted representation of *object* as a string.  *indent*,
   *width*, *depth*, *compact*, *expand*, *sort_dicts* and *underscore_numbers* are
   passed to the :class:`PrettyPrinter` constructor as formatting parameters
   and their meanings are as described in the documentation above.


.. function:: isreadable(object)

   .. index:: pair: built-in function; eval

   Determine if the formatted representation of *object* is "readable", or can be
   used to reconstruct the value using :func:`eval`.  This always returns ``False``
   for recursive objects.

      >>> pprint.isreadable(stuff)
      False


.. function:: isrecursive(object)

   Determine if *object* requires a recursive representation.  This function is
   subject to the same limitations as noted in :func:`saferepr` below and may raise an
   :exc:`RecursionError` if it fails to detect a recursive object.


.. function:: saferepr(object)

   Return a string representation of *object*, protected against recursion in
   some common data structures, namely instances of :class:`dict`, :class:`list`
   and :class:`tuple` or subclasses whose ``__repr__`` has not been overridden.  If the
   representation of object exposes a recursive entry, the recursive reference
   will be represented as ``<Recursion on typename with id=number>``.  The
   representation is not otherwise formatted.

   >>> pprint.saferepr(stuff)
   "[<Recursion on list with id=...>, 'spam', 'eggs', 'lumberjack', 'knights', 'ni']"

.. _prettyprinter-objects:

PrettyPrinter Objects
---------------------

.. index:: single: ...; placeholder

.. class:: PrettyPrinter(indent=1, width=80, depth=None, stream=None, *, \
                         compact=False, expand=False, sort_dicts=True, \
                         underscore_numbers=False)

   Construct a :class:`PrettyPrinter` instance.

   Arguments have the same meaning as for :func:`~pprint.pp`.
   Note that they are in a different order, and that *sort_dicts* defaults to ``True``.

   >>> import pprint
   >>> stuff = ['spam', 'eggs', 'lumberjack', 'knights', 'ni']
   >>> stuff.insert(0, stuff[:])
   >>> pp = pprint.PrettyPrinter(indent=4)
   >>> pp.pprint(stuff)
   [   ['spam', 'eggs', 'lumberjack', 'knights', 'ni'],
       'spam',
       'eggs',
       'lumberjack',
       'knights',
       'ni']
   >>> pp = pprint.PrettyPrinter(width=41, compact=True)
   >>> pp.pprint(stuff)
   [['spam', 'eggs', 'lumberjack',
     'knights', 'ni'],
    'spam', 'eggs', 'lumberjack', 'knights',
    'ni']
   >>> pp = pprint.PrettyPrinter(width=41, expand=True, indent=3)
   >>> pp.pprint(stuff)
   [
      [
         'spam',
         'eggs',
         'lumberjack',
         'knights',
         'ni',
      ],
      'spam',
      'eggs',
      'lumberjack',
      'knights',
      'ni',
   ]
   >>> tup = ('spam', ('eggs', ('lumberjack', ('knights', ('ni', ('dead',
   ... ('parrot', ('fresh fruit',))))))))
   >>> pp = pprint.PrettyPrinter(depth=6)
   >>> pp.pprint(tup)
   ('spam', ('eggs', ('lumberjack', ('knights', ('ni', ('dead', (...)))))))


   .. versionchanged:: 3.4
      Added the *compact* parameter.

   .. versionchanged:: 3.8
      Added the *sort_dicts* parameter.

   .. versionchanged:: 3.10
      Added the *underscore_numbers* parameter.

   .. versionchanged:: 3.11
      No longer attempts to write to :data:`!sys.stdout` if it is ``None``.

   .. versionchanged:: 3.15
      Added the *expand* parameter.

   .. soft-deprecated:: next
      No new features will be added to :class:`!PrettyPrinter`.  New code
      should use :class:`Printer`, which supports the
      :ref:`pretty print protocol <pprint-protocol>`.


:class:`PrettyPrinter` instances have the following methods:


.. method:: PrettyPrinter.pformat(object)

   Return the formatted representation of *object*.  This takes into account the
   options passed to the :class:`PrettyPrinter` constructor.


.. method:: PrettyPrinter.pprint(object)

   Print the formatted representation of *object* on the configured stream,
   followed by a newline.

The following methods provide the implementations for the corresponding
functions of the same names.  Using these methods on an instance is slightly
more efficient since new :class:`PrettyPrinter` objects don't need to be
created.


.. method:: PrettyPrinter.isreadable(object)

   .. index:: pair: built-in function; eval

   Determine if the formatted representation of the object is "readable," or can be
   used to reconstruct the value using :func:`eval`.  Note that this returns
   ``False`` for recursive objects.  If the *depth* parameter of the
   :class:`PrettyPrinter` is set and the object is deeper than allowed, this
   returns ``False``.


.. method:: PrettyPrinter.isrecursive(object)

   Determine if the object requires a recursive representation.

This method is provided as a hook to allow subclasses to modify the way objects
are converted to strings.  The default implementation uses the internals of the
:func:`saferepr` implementation.


.. method:: PrettyPrinter.format(object, context, maxlevels, level)

   Returns three values: the formatted version of *object* as a string, a flag
   indicating whether the result is readable, and a flag indicating whether
   recursion was detected.  The first argument is the object to be presented.  The
   second is a dictionary which contains the :func:`id` of objects that are part of
   the current presentation context (direct and indirect containers for *object*
   that are affecting the presentation) as the keys; if an object needs to be
   presented which is already represented in *context*, the third return value
   should be ``True``.  Recursive calls to the :meth:`.format` method should add
   additional entries for containers to this dictionary.  The third argument,
   *maxlevels*, gives the requested limit to recursion; this will be ``0`` if there
   is no requested limit.  This argument should be passed unmodified to recursive
   calls. The fourth argument, *level*, gives the current level; recursive calls
   should be passed a value less than that of the current call.


.. _pprint-example:

Example
-------

To demonstrate several uses of the :func:`~pprint.pp` function and its parameters,
let's fetch information about a project from `PyPI <https://pypi.org>`_::

   >>> import json
   >>> import pprint
   >>> from urllib.request import urlopen
   >>> with urlopen('https://pypi.org/pypi/sampleproject/1.2.0/json') as resp:
   ...     project_info = json.load(resp)['info']

In its basic form, :func:`~pprint.pp` shows the whole object::

   >>> pprint.pp(project_info)
   {'author': 'The Python Packaging Authority',
    'author_email': 'pypa-dev@googlegroups.com',
    'bugtrack_url': None,
    'classifiers': ['Development Status :: 3 - Alpha',
                    'Intended Audience :: Developers',
                    'License :: OSI Approved :: MIT License',
                    'Programming Language :: Python :: 2',
                    'Programming Language :: Python :: 2.6',
                    'Programming Language :: Python :: 2.7',
                    'Programming Language :: Python :: 3',
                    'Programming Language :: Python :: 3.2',
                    'Programming Language :: Python :: 3.3',
                    'Programming Language :: Python :: 3.4',
                    'Topic :: Software Development :: Build Tools'],
    'description': 'A sample Python project\n'
                   '=======================\n'
                   '\n'
                   'This is the description file for the project.\n'
                   '\n'
                   'The file should use UTF-8 encoding and be written using '
                   'ReStructured Text. It\n'
                   'will be used to generate the project webpage on PyPI, and '
                   'should be written for\n'
                   'that purpose.\n'
                   '\n'
                   'Typical contents for this file would include an overview of '
                   'the project, basic\n'
                   'usage examples, etc. Generally, including the project '
                   'changelog in here is not\n'
                   'a good idea, although a simple "What\'s New" section for the '
                   'most recent version\n'
                   'may be appropriate.',
    'description_content_type': None,
    'docs_url': None,
    'download_url': 'UNKNOWN',
    'downloads': {'last_day': -1, 'last_month': -1, 'last_week': -1},
    'home_page': 'https://github.com/pypa/sampleproject',
    'keywords': 'sample setuptools development',
    'license': 'MIT',
    'maintainer': None,
    'maintainer_email': None,
    'name': 'sampleproject',
    'package_url': 'https://pypi.org/project/sampleproject/',
    'platform': 'UNKNOWN',
    'project_url': 'https://pypi.org/project/sampleproject/',
    'project_urls': {'Download': 'UNKNOWN',
                     'Homepage': 'https://github.com/pypa/sampleproject'},
    'release_url': 'https://pypi.org/project/sampleproject/1.2.0/',
    'requires_dist': None,
    'requires_python': None,
    'summary': 'A sample Python project',
    'version': '1.2.0'}

The result can be limited to a certain *depth* (ellipsis is used for deeper
contents)::

   >>> pprint.pp(project_info, depth=1)
   {'author': 'The Python Packaging Authority',
    'author_email': 'pypa-dev@googlegroups.com',
    'bugtrack_url': None,
    'classifiers': [...],
    'description': 'A sample Python project\n'
                   '=======================\n'
                   '\n'
                   'This is the description file for the project.\n'
                   '\n'
                   'The file should use UTF-8 encoding and be written using '
                   'ReStructured Text. It\n'
                   'will be used to generate the project webpage on PyPI, and '
                   'should be written for\n'
                   'that purpose.\n'
                   '\n'
                   'Typical contents for this file would include an overview of '
                   'the project, basic\n'
                   'usage examples, etc. Generally, including the project '
                   'changelog in here is not\n'
                   'a good idea, although a simple "What\'s New" section for the '
                   'most recent version\n'
                   'may be appropriate.',
    'description_content_type': None,
    'docs_url': None,
    'download_url': 'UNKNOWN',
    'downloads': {...},
    'home_page': 'https://github.com/pypa/sampleproject',
    'keywords': 'sample setuptools development',
    'license': 'MIT',
    'maintainer': None,
    'maintainer_email': None,
    'name': 'sampleproject',
    'package_url': 'https://pypi.org/project/sampleproject/',
    'platform': 'UNKNOWN',
    'project_url': 'https://pypi.org/project/sampleproject/',
    'project_urls': {...},
    'release_url': 'https://pypi.org/project/sampleproject/1.2.0/',
    'requires_dist': None,
    'requires_python': None,
    'summary': 'A sample Python project',
    'version': '1.2.0'}

Additionally, maximum character *width* can be suggested. If a long object
cannot be split, the specified width will be exceeded::

   >>> pprint.pp(project_info, depth=1, width=60)
   {'author': 'The Python Packaging Authority',
    'author_email': 'pypa-dev@googlegroups.com',
    'bugtrack_url': None,
    'classifiers': [...],
    'description': 'A sample Python project\n'
                   '=======================\n'
                   '\n'
                   'This is the description file for the '
                   'project.\n'
                   '\n'
                   'The file should use UTF-8 encoding and be '
                   'written using ReStructured Text. It\n'
                   'will be used to generate the project '
                   'webpage on PyPI, and should be written '
                   'for\n'
                   'that purpose.\n'
                   '\n'
                   'Typical contents for this file would '
                   'include an overview of the project, '
                   'basic\n'
                   'usage examples, etc. Generally, including '
                   'the project changelog in here is not\n'
                   'a good idea, although a simple "What\'s '
                   'New" section for the most recent version\n'
                   'may be appropriate.',
    'description_content_type': None,
    'docs_url': None,
    'download_url': 'UNKNOWN',
    'downloads': {...},
    'home_page': 'https://github.com/pypa/sampleproject',
    'keywords': 'sample setuptools development',
    'license': 'MIT',
    'maintainer': None,
    'maintainer_email': None,
    'name': 'sampleproject',
    'package_url': 'https://pypi.org/project/sampleproject/',
    'platform': 'UNKNOWN',
    'project_url': 'https://pypi.org/project/sampleproject/',
    'project_urls': {...},
    'release_url': 'https://pypi.org/project/sampleproject/1.2.0/',
    'requires_dist': None,
    'requires_python': None,
    'summary': 'A sample Python project',
    'version': '1.2.0'}

Lastly, we can format like pretty-printed JSON with the *expand* parameter.
Best results are achieved with a higher *indent* value::

   >>> pprint.pp(project_info, indent=4, expand=True)
   {
      'author': 'The Python Packaging Authority',
      'author_email': 'pypa-dev@googlegroups.com',
      'bugtrack_url': None,
      'classifiers': [
         'Development Status :: 3 - Alpha',
         'Intended Audience :: Developers',
         'License :: OSI Approved :: MIT License',
         'Programming Language :: Python :: 2',
         'Programming Language :: Python :: 2.6',
         'Programming Language :: Python :: 2.7',
         'Programming Language :: Python :: 3',
         'Programming Language :: Python :: 3.2',
         'Programming Language :: Python :: 3.3',
         'Programming Language :: Python :: 3.4',
         'Topic :: Software Development :: Build Tools',
      ],
      'description': 'A sample Python project\n'
      '=======================\n'
      '\n'
      'This is the description file for the project.\n'
      '\n'
      'The file should use UTF-8 encoding and be written using ReStructured '
      'Text. It\n'
      'will be used to generate the project webpage on PyPI, and should be '
      'written for\n'
      'that purpose.\n'
      '\n'
      'Typical contents for this file would include an overview of the project, '
      'basic\n'
      'usage examples, etc. Generally, including the project changelog in here '
      'is not\n'
      'a good idea, although a simple "What\'s New" section for the most recent '
      'version\n'
      'may be appropriate.',
      'description_content_type': None,
      'docs_url': None,
      'download_url': 'UNKNOWN',
      'downloads': {'last_day': -1, 'last_month': -1, 'last_week': -1},
      'dynamic': None,
      'home_page': 'https://github.com/pypa/sampleproject',
      'keywords': 'sample setuptools development',
      'license': 'MIT',
      'license_expression': None,
      'license_files': None,
      'maintainer': None,
      'maintainer_email': None,
      'name': 'sampleproject',
      'package_url': 'https://pypi.org/project/sampleproject/',
      'platform': 'UNKNOWN',
      'project_url': 'https://pypi.org/project/sampleproject/',
      'project_urls': {
         'Download': 'UNKNOWN',
         'Homepage': 'https://github.com/pypa/sampleproject',
      },
      'provides_extra': None,
      'release_url': 'https://pypi.org/project/sampleproject/1.2.0/',
      'requires_dist': None,
      'requires_python': None,
      'summary': 'A sample Python project',
      'version': '1.2.0',
      'yanked': False,
      'yanked_reason': None,
   }


.. _pprint-protocol:

The pretty print protocol
-------------------------

.. versionadded:: next

A class describes the pretty printed form of its instances with a
:meth:`~object.__pprint__` method.  The method yields a *description stream*:
the object's items, optionally preceded by a :class:`Layout` and separated into
sections by the :data:`VALUES`, :data:`KWARGS` and :data:`ITEMS` markers.  A
*printer* interprets the stream and decides where the line breaks go, so the
method never handles layout itself.

For example:

.. code-block:: pycon
   :force:

   >>> import pprint
   >>> class Bass:
   ...     def __init__(self, model, strings=4, tuning=('E', 'A', 'D', 'G')):
   ...         self.model = model
   ...         self.strings = strings
   ...         self.tuning = tuning
   ...
   ...     def __pprint__(self):
   ...         yield self.model
   ...         yield pprint.KWARGS
   ...         yield 'strings', self.strings, 4
   ...         yield 'tuning', self.tuning, ('E', 'A', 'D', 'G')
   ...
   >>> print(f'{Bass("jazz")!p}')
   Bass('jazz')
   >>> stingray = Bass('stingray', 5, ('B', 'E', 'A', 'D', 'G'))
   >>> print(f'{stingray!p}')
   Bass('stingray', strings=5, tuning=('B', 'E', 'A', 'D', 'G'))
   >>> for line in pprint.Printer(width=30)(stingray):
   ...     print(line)
   ...
   Bass(
       'stingray',
       strings=5,
       tuning=(
           'B',
           'E',
           'A',
           'D',
           'G',
       ),
   )

Keyword items whose value equals their default are omitted.  The ``!p``
conversion in :ref:`f-strings <f-strings>` and :meth:`str.format` pretty prints
a value with the default printer, or with a printer given as
``f'{obj!p:{printer}}'``.

A *printer* is any callable that takes the object to print as its only
argument and returns an iterable of strings, one for each line of output,
without line endings.  The built-in and standard library types implement
:meth:`~object.__pprint__`, as do classes made by :func:`dataclasses.dataclass`
and :func:`collections.namedtuple`.  An object without a usable
:meth:`~object.__pprint__` is printed with :func:`repr`.


Printers
^^^^^^^^

.. class:: Printer(indent=4, width=78, depth=None, *, compact=False, \
                   expand=Expand.FIT, sort_dicts=True, number_format=None)

   The default printer.  Calling an instance with an object returns an
   iterable of the lines of its pretty printed form.

   The arguments have the same meanings as for :class:`PrettyPrinter`, with
   these differences:

   * *expand* takes a member of :class:`Expand`.
   * *compact* packs positional items onto as few lines as possible with every
     *expand* mode.  An item that does not fit on one line gets lines of its
     own, and with :attr:`Expand.ALWAYS` a non-empty container is never packed.
   * *number_format* replaces *underscore_numbers*.  It is a
     :ref:`format specification <formatspec>` that is passed to :func:`format`
     for each :class:`FormattableNumber`, which includes every :class:`int` and
     :class:`float`.  For example, ``'_'`` groups digits as
     ``underscore_numbers=True`` does, and ``','`` groups them with commas.  If
     :func:`format` raises an exception, or *number_format* is ``None``, the
     number is printed with :func:`repr`.
   * There is no *stream* argument, since a printer returns its lines.

   The default *width* of 78 keeps the output within the line length that
   :pep:`8` recommends.

   The printer calls :func:`decompose` on every object it prints, including
   each item, key and value, so nested objects wrap inside their containers at
   any depth.  When *sort_dicts* is true, the items of an object whose
   :class:`Layout` is :attr:`~Layout.sortable` are sorted: key/value items by
   key, positional items by value, and keyword items by name, after the others.
   Items that cannot be compared with each other are sorted by their one-line
   pretty printed form.

   ::

      >>> stuff = {'stingray': ['B', 'E', 'A', 'D', 'G'],
      ...          'precision': ['E', 'A', 'D', 'G'], 'jazz': 1234567.5}
      >>> for line in pprint.Printer(width=40, number_format=',')(stuff):
      ...     print(line)
      ...
      {
          'jazz': 1,234,567.5,
          'precision': ['E', 'A', 'D', 'G'],
          'stingray': [
              'B',
              'E',
              'A',
              'D',
              'G',
          ],
      }

   .. versionadded:: next


.. class:: Expand

   An :class:`~enum.Enum` of the ways a :class:`Printer` lays out a container
   that does not fit on one line.  In every mode, an object that fits on one
   line is printed on one line.

   .. attribute:: NEVER

      The items follow the open bracket and are aligned under it, as
      :class:`PrettyPrinter` lays them out by default.  *indent* is used only
      for a value that starts on the line after a wrapped key.

   .. attribute:: FIT

      Each item is on its own line, indented by *indent*, with a trailing
      separator, and the close bracket is on a line of its own.  A nested
      container is laid out this way only if it does not fit on one line
      itself.  This is the default.

   .. attribute:: ALWAYS

      The same as :attr:`FIT`, except that once a container does not fit,
      every non-empty container inside it is laid out this way too.

   .. versionadded:: next


The description stream
^^^^^^^^^^^^^^^^^^^^^^

The items that a :meth:`~object.__pprint__` method yields are read in
sections.  The stream starts in the :data:`VALUES` section, and a section
marker changes how the items that follow it are read, until the next marker.
Markers may appear in any order, any number of times, and items are printed in
the order they are yielded.

.. data:: VALUES

   Each item that follows is a positional value, printed as ``value``.  Tuples
   are values too.

.. data:: KWARGS

   Each item that follows is a ``(name, value)`` or ``(name, value, default)``
   tuple, printed as ``name=value``.  *name* is a :class:`str`, printed as is.
   An item is omitted when ``value == default`` is true.  If that comparison
   raises an exception, the item is shown with a placeholder, such as
   ``arr=<error comparing to default: ValueError>``.

.. data:: ITEMS

   Each item that follows is a ``(key, value)`` tuple, printed as
   ``key: value``.  The key is pretty printed like any other value.

.. data:: DELEGATE

   When it is the first item in the stream, the next item is printed in place
   of the object.  For example, :class:`collections.UserDict` delegates to its
   underlying :class:`dict`.

The section markers, :data:`DELEGATE` and :data:`LEAF` are :class:`sentinel`
objects.

The default printer reads the stream permissively.  An item that does not fit
its section, such as a 4-tuple under :data:`KWARGS`, is a value.  Any object
that is not part of this vocabulary is a value too, so a marker that only
another printer understands is printed with its :func:`repr`.  A
:class:`Layout` or :data:`DELEGATE` that is not the first item is a value.  The
printer does not check that its output is valid Python.

.. class:: Layout(*, name=None, open=None, close=None, sep=',', empty=None, \
                  single_close=None, recursion='...', sortable=False, \
                  hug=False, hints=None)

   Describes an object's *chrome*: the name and brackets around its items, the
   separator between them, and a few special cases.  A
   :meth:`~object.__pprint__` method sets the chrome of its object by yielding
   a :class:`!Layout` as the first item of the stream.  All of the arguments
   are optional, and are available as attributes of the same names.

   *name* is used in the default brackets, and is ``type(obj).__name__`` when
   not given.  *open* and *close* are the text before and after the items.
   By default, the object is printed as its name followed by the items in
   parentheses, or in ``({...})`` when every item is a key/value item, as in
   ``Counter({'a': 1})``.

   *sep* is the separator between items.  When the items fit on one line, a
   space follows each separator.

   *empty* is the text printed when there are no items, *open* followed by
   *close* by default.  *single_close* replaces *close* when there is exactly
   one item, as in the ``',)'`` of a one-element tuple.  *recursion* is printed
   for a reference cycle back to the object.

   .. attribute:: sortable

      Whether a printer may sort the items, because their order is not
      significant.

   .. attribute:: hug

      Whether a printer keeps the other items on the opening and closing lines
      when exactly one item is a container that does not fit.  It affects
      :attr:`Expand.FIT` and :attr:`Expand.ALWAYS`.  For example,
      :class:`collections.defaultdict` sets it, so that it prints as:

      .. code-block:: text

         defaultdict(<class 'list'>, {
             'precision': ['E', 'A', 'D', 'G'],
             'stingray': ['B', 'E', 'A', 'D', 'G'],
         })

   .. attribute:: hints

      A mapping of hints for particular printers.  By convention, each key
      names the printer that reads it, as in ``'html.role'``.  The default
      printer ignores them.

   .. versionadded:: next

.. class:: Keyword(name, value, default=<missing>)

   A keyword item, printed as ``name=value``, and omitted when *value* equals
   *default*.  It can be yielded in any section.

   .. versionadded:: next

.. class:: Entry(key, value)

   A key/value item, printed as ``key: value``.  It can be yielded in any
   section.

   .. versionadded:: next

.. class:: BreakableString(value)
           BreakableBytes(value)

   A :class:`str` or :class:`bytes` value that a printer may split across
   lines.  The default printer prints its :func:`repr`, split into adjacent
   literals to fit the width.  :class:`str` and :class:`bytes` describe
   themselves by delegating to these, and any other class can yield them to
   get a wrappable string.

   .. versionadded:: next

.. class:: FormattableNumber(value)

   A number that a printer may format.  The default printer formats it with
   its *number_format* option.  :class:`int` and :class:`float` describe
   themselves by delegating to it.

   .. versionadded:: next

.. type:: DescriptionType

   A type alias for the result of a :meth:`~object.__pprint__` method, defined
   as ``type DescriptionType = Iterable[object]``.

   .. versionadded:: next


Decomposing objects
^^^^^^^^^^^^^^^^^^^

.. function:: decompose(obj)

   Find the usable :meth:`~object.__pprint__` method of ``type(obj)``, run it,
   and read one level of its stream.  Return a 2-tuple:

   * ``(LEAF, None)`` if *obj* is a leaf, whose type has no usable
     :meth:`~object.__pprint__` method.
   * ``(DELEGATE, value)`` if the object delegates to *value*.
   * Otherwise, a :class:`Layout` with every attribute filled in, and a list of
     items, each a plain value, a :class:`Keyword` or an :class:`Entry`.
     Keyword items equal to their defaults are removed, and the section
     markers do not appear.

   :func:`!decompose` does not recurse into the items, and does not depend on
   any printer setting.  Other printers can call it to read a stream the same
   way the default printer does::

      >>> layout, items = pprint.decompose({'a': 1})
      >>> layout.open, layout.close, layout.sortable
      ('{', '}', True)
      >>> items
      [Entry(key='a', value=1)]
      >>> pprint.decompose(42)
      (pprint.DELEGATE, FormattableNumber(42))
      >>> pprint.decompose(object())
      (pprint.LEAF, None)

   .. versionadded:: next

.. data:: LEAF

   Returned by :func:`decompose` for an object whose type has no usable
   :meth:`~object.__pprint__` method, including the marker classes
   :class:`BreakableString`, :class:`BreakableBytes` and
   :class:`FormattableNumber`.  It is not part of the stream vocabulary.

   .. versionadded:: next
