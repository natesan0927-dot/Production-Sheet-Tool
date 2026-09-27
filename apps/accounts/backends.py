"""Signing in by name, however the name was typed.

Django matches a username exactly, so "Rahul" was refused for the account
"rahul". People type their own name the way it is written, and phone keyboards
capitalise the first letter of a box on their own, so the exact match turned
away the very people it was meant to let in — with a message that said the
account did not exist.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None

        typed = username.strip()
        matches = list(User._default_manager.filter(**{f"{User.USERNAME_FIELD}__iexact": typed})[:2])

        if len(matches) > 1:
            # Two accounts that differ only by case: only an exact match is safe.
            matches = [user for user in matches if getattr(user, User.USERNAME_FIELD) == typed]

        if not matches:
            # Spend the same time hashing as a real attempt would, so the
            # response does not reveal whether the name exists.
            User().set_password(password)
            return None

        user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
