"""Pre-populate cache with metadata for common external Parameterized classes."""

from __future__ import annotations

import logging

from param_lsp._analyzer.external_class_inspector import ExternalClassInspector
from param_lsp.cache import external_library_cache

logger = logging.getLogger(__name__)

# Common external classes that users frequently need
COMMON_EXTERNAL_CLASSES = [
    # Panel widgets
    "panel.widgets.IntSlider",
    "panel.widgets.FloatSlider",
    "panel.widgets.TextInput",
    "panel.widgets.TextAreaInput",
    "panel.widgets.Checkbox",
    "panel.widgets.Select",
    "panel.widgets.MultiSelect",
    "panel.widgets.Button",
    "panel.widgets.DatetimeInput",
    "panel.widgets.DatePicker",
    "panel.widgets.FileInput",
    # Panel panes
    "panel.pane.Markdown",
    "panel.pane.HTML",
    "panel.pane.Image",
    "panel.pane.Bokeh",
    "panel.pane.Matplotlib",
    # Panel layouts
    "panel.layout.Row",
    "panel.layout.Column",
    "panel.layout.Tabs",
    "panel.layout.Accordion",
    # HoloViews elements
    "holoviews.Curve",
    "holoviews.Scatter",
    "holoviews.Area",
    "holoviews.Bar",
    "holoviews.Histogram",
    "holoviews.Image",
    "holoviews.QuadMesh",
    "holoviews.HeatMap",
    "holoviews.Points",
    "holoviews.Path",
    "holoviews.Polygons",
    # HoloViews operations
    "holoviews.operation.datashader.regrid",
    "holoviews.operation.datashader.rasterize",
]


class CachePopulator:
    """Pre-populate the existing cache with common external classes."""

    def __init__(self):
        self.inspector = ExternalClassInspector()

    def populate_cache_for_classes(self, class_paths: list[str]) -> int:
        """Populate cache for a list of class paths.

        Args:
            class_paths: List of full class paths (e.g., "panel.widgets.IntSlider")

        Returns:
            Number of classes successfully cached
        """
        cached_count = 0

        for class_path in class_paths:
            try:
                logger.info(f"Caching metadata for {class_path}")
                class_info = self.inspector._introspect_external_class_runtime(class_path)

                if class_info:
                    # Extract library name from class path
                    library_name = class_path.split(".")[0]
                    # Store in the existing cache system
                    external_library_cache.set(library_name, class_path, class_info)
                    cached_count += 1
                    logger.info(f"Successfully cached metadata for {class_path}")
                else:
                    logger.warning(f"Could not introspect {class_path}")

            except Exception as e:
                logger.error(f"Error caching metadata for {class_path}: {e}")

        return cached_count

    def populate_common_cache(self) -> int:
        """Pre-populate cache with common external classes.

        Returns:
            Number of classes successfully cached
        """
        logger.info(f"Pre-populating cache for {len(COMMON_EXTERNAL_CLASSES)} common classes")
        cached_count = self.populate_cache_for_classes(COMMON_EXTERNAL_CLASSES)
        logger.info(f"Successfully cached {cached_count} common external classes")
        return cached_count


def main():
    """Pre-populate cache with common external classes."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    populator = CachePopulator()

    try:
        cached_count = populator.populate_common_cache()
        print(f"Cache population completed successfully! Cached {cached_count} classes.")
    except Exception as e:
        print(f"Error populating cache: {e}")
        raise


if __name__ == "__main__":
    main()
