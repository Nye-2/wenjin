"""Application-layer handlers package.

Keep this package import side-effect free.

Import concrete handlers from their modules instead of re-exporting them here;
otherwise importing a single submodule can trigger unrelated handler imports and
reintroduce circular dependencies during test collection and app startup.
"""

__all__: list[str] = []
