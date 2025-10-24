"""
Simulate an external library with inheritance to test cache generation.
This mimics the Panel WidgetBox → ListPanel → ListLike hierarchy.
"""
import param


class ListLike(param.Parameterized):
    """Base class with 'objects' parameter (like Panel's ListLike)."""
    objects = param.List(default=[])


class ListPanel(ListLike):
    """Middle class in inheritance chain."""
    scroll = param.Boolean(default=False)


class WidgetBox(ListPanel):
    """Child class that uses @param.depends on inherited 'objects'."""
    disabled = param.Boolean(default=False)
    horizontal = param.Boolean(default=False)

    @param.depends('disabled', 'objects', watch=True)
    def _update_state(self) -> None:
        """Method that depends on both local and inherited parameters."""
        pass
