import logging
from typing import Any, Dict

from social_core.backends.base import BaseAuth

logger = logging.getLogger(__name__)


def relink_social_user(
    backend: BaseAuth,
    uid: str,
    user=None,
    *args: Any,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Allow authenticated users to reclaim an existing social account."""
    storage = backend.strategy.storage
    social = storage.user.get_social_auth(backend.name, uid)

    if social:
        if user:
            if social.user != user:
                logger.info(
                    "Reassigning %s account from user %s to %s",
                    backend.name,
                    social.user_id,
                    user.id,
                )
                social.user = user
                social.save(update_fields=['user'])
        else:
            user = social.user
    return {
        "social": social,
        "user": user,
        "is_new": user is None,
        "new_association": social is None,
    }
