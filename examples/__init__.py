"""A complete example service built on the kernel.

This is a real application, not a snippet: it declares one bounded context,
assembles it with dependency-injector, and is exercised by
``tests/test_examples.py``, so nothing here can drift away from the kernel's
actual API without a gate going red.

Read ``examples/README.md`` for the walkthrough, or start at
``examples/composition/container.py`` to see how the process is assembled.
"""
