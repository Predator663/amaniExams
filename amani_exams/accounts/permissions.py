from rest_framework.permissions import BasePermission


class NotForcedPasswordChange(BasePermission):
    """Students must set a new password on first login (AUTH-05). Until they do, every
    endpoint except those that opt in (`allow_forced_password_change = True`) is refused."""

    message = "You must change your password first."

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.must_change_password):
            return True
        return bool(getattr(view, "allow_forced_password_change", False))


class _Role(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and self.check(u)):
            return False
        # Views that set their own permission_classes replace the defaults, so the
        # "must change password first" rule (AUTH-05) is enforced here as well.
        if u.must_change_password and not getattr(view, "allow_forced_password_change", False):
            return False
        return True

    def check(self, u):
        raise NotImplementedError


class IsStudent(_Role):
    def check(self, u):
        return u.is_student


class IsStaffUser(_Role):  # teacher, admin, super admin
    def check(self, u):
        return u.is_staff_role


class IsAdminRole(_Role):  # admin, super admin
    def check(self, u):
        return u.is_admin_role


class IsSuperAdmin(_Role):
    def check(self, u):
        return u.role == "super_admin"


class IsAnyUser(_Role):  # any logged-in user (still blocked while a forced password change is pending)
    def check(self, u):
        return True
