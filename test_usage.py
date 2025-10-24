"""
Test file that uses the external library classes.
This simulates checking panel/layout/base.py
"""

from __future__ import annotations

import param

from test_library import WidgetBox


class MyWidget(WidgetBox):
    """User class extending WidgetBox."""

    @param.depends("objects", watch=True)
    def my_method(self):
        """This should work since objects is inherited from ListLike."""
