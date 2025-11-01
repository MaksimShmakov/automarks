from django.core.exceptions import PermissionDenied


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

            # Fallback: map via groups if role is missing
            if not role and hasattr(user, "groups"):
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
