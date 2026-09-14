"""Runtime settings instance for the Admin demo."""

from typing import cast

import oldman.conf as conf
from config.schemas import Settings

settings = cast(Settings, conf.settings)
