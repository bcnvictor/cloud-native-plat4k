"""
Resource related schemas.
"""
from shared.models import ResourceBase, ResourceCreate, ResourceResponse

# Re-exporting from shared models to keep structure consistent
__all__ = ["ResourceBase", "ResourceCreate", "ResourceResponse"]
