"""Compatibility entry point for the Option Chaser MVP V2 core.

Implementation lives in ``option_chaser.v2``. Existing callers may continue
importing from this module. New public symbols only need to be added to
``option_chaser.v2.__all__``; this facade does not need to be rewritten.
"""

from option_chaser.v2 import *  # noqa: F401,F403
from option_chaser.v2 import __all__
