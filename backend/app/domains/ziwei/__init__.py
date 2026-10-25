"""紫微斗数域（三合派口径）。"""

from app.domains.ziwei.engine import calculate
from app.domains.ziwei.schemas import ZiweiCalculateIn, ZiweiConvention, ZiweiInput

__all__ = ["calculate", "ZiweiCalculateIn", "ZiweiConvention", "ZiweiInput"]
