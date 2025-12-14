from django.core.exceptions import PermissionDenied


BOT_OPERATORS_GROUP = "Bot Operators"
BOT_OPERATORS_ROLE = "bot_user"


def require_roles(*allowed):
    """Role-based access with pragmatic fallbacks.

    - Allows superuser regardless of role.
    - Uses `user.profile.role` if present.
    - Falls back to Django groups mapping (Администратор/Маркетолог/Аналитик).
    """

    GROUP_TO_ROLE = {
        "Администратор": "admin",
        "Маркетолог": "marketer",
        "Аналитик": "analyst",
        # Optional aliases
        "Менеджер": "manager",
        BOT_OPERATORS_GROUP: BOT_OPERATORS_ROLE,
    }

    def decorator(view):
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied

            # Superuser bypass
            if getattr(user, "is_superuser", False):
                return view(request, *args, **kwargs)

            # Primary: profile role
            role = getattr(getattr(user, "profile", None), "role", None)

            # Fallback or override: map via groups when role is missing or insufficient
            if (not role or role not in allowed) and hasattr(user, "groups"):
                for grp_name, mapped in GROUP_TO_ROLE.items():
                    try:
                        if user.groups.filter(name=grp_name).exists():
                            role = mapped
                            break
                    except Exception:
                        pass

            if role not in allowed:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator
