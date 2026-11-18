"""Safe Phase 7 demo configuration flags."""
import os

DEMO_API = os.getenv("DEMO_API", "off").strip().lower() == "on"
DEMO_CONFIRM = os.getenv("DEMO_CONFIRM", "").strip()
USE_AI = os.getenv("USE_AI", "off").strip().lower()
