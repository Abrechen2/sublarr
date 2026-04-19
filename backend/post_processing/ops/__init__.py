"""Auto-import all op modules so @register_op decorators fire.

Each submodule registers its op classes with ``_OP_REGISTRY`` via the
``@register_op`` decorator on import; simply importing the submodules here
is enough to surface every curated op to the pipeline + API.
"""

from post_processing.ops import discord_notify  # noqa: F401
from post_processing.ops import text_ops  # noqa: F401
from post_processing.ops import webhook  # noqa: F401
