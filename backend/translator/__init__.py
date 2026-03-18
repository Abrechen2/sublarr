"""Translator package — subtitle translation pipeline.

All public symbols re-exported for backward compatibility.
External code uses: from translator import X

Symbols patched in tests (patch("translator.X") targets this namespace):
    get_settings, get_media_streams, select_best_subtitle_stream,
    extract_subtitle_stream, _translate_with_manager, _get_quality_config
These are re-exported here AND accessed lazily by core.py so that
unittest.mock.patch("translator.X") correctly intercepts them.
"""

# Re-exports for external callers and test-patchable symbols
from ass_utils import (  # noqa: F401
    extract_subtitle_stream,
    get_media_streams,
    select_best_subtitle_stream,
)
from config import get_settings  # noqa: F401
from translator._helpers import (  # noqa: F401
    _get_quality_config,
    check_disk_space,
    find_external_source_sub,
)
from translator.cache import (  # noqa: F401
    _apply_translation_cache,
    _store_translations_in_cache,
)
from translator.core import (  # noqa: F401
    Translator,
    _translate_external_ass,
    _translate_with_manager,
    translate_ass,
    translate_file,
    translate_srt_from_file,
    translate_srt_from_stream,
)
from translator.jobs import (  # noqa: F401
    scan_directory,
    submit_translation_job,
)
from translator.output_paths import (  # noqa: F401
    detect_existing_target,
    detect_existing_target_for_lang,
    get_forced_output_path,
    get_output_path,
    get_output_path_for_lang,
)
from translator.quality import (  # noqa: F401
    validate_translation_output,
)
