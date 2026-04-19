"""Post-processing pipeline package (Plan B6).

Fires a user-configured ordered list of ops against the saved subtitle after
three save-path triggers: ``after_download``, ``after_translate``,
``after_sync``. Curated ops ship in :mod:`post_processing.ops`; an opt-in
shell-script escape hatch lives in :mod:`post_processing.shell_runner`.
"""

from post_processing.pipeline import PostProcessingPipeline, run_trigger  # noqa: F401
