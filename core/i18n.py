"""Translation hook for core modules.

Core code calls ``_()`` from here instead of relying on the ``_`` builtin that
``gettext.install()`` creates, so it also works in the server and in tests.
"""
import gettext

_translation: gettext.NullTranslations = gettext.NullTranslations()


def set_translation(translation: gettext.NullTranslations | None):
    global _translation
    _translation = translation if translation is not None else gettext.NullTranslations()


def _(message: str) -> str:
    return _translation.gettext(message)
