import simple_history
from modeltranslation.translator import TranslationOptions, register

from enterprise_catalog.apps.academy.models import Academy, Tag


@register(Academy)
class AcademyTranslationOptions(TranslationOptions):
    fields = ('title', 'short_description', 'long_description',)


@register(Tag)
class TagTranslationOptions(TranslationOptions):
    fields = ('title', 'description',)


# https://django-simple-history.readthedocs.io/en/latest/common_issues.html#usage-with-django-modeltranslation
simple_history.register(Academy, inherit=True)
