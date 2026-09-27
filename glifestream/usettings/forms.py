"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from typing import Any

from django.conf import settings
from django.forms import CheckboxSelectMultiple, ChoiceField, ModelForm
from django.utils.translation import get_language_info
from django.utils.translation import gettext_lazy as _

from glifestream.gauth.models import UserProfile
from glifestream.stream.models import List


class ListForm(ModelForm):
    class Meta:
        model = List
        exclude = ('user',)
        labels = {'services': _('Services')}
        widgets = {'services': CheckboxSelectMultiple}


def _language_choices() -> list[tuple[str, Any]]:
    # Each language names itself, so it can be found whatever the current one.
    return [('', _('Browser default'))] + [
        (code, get_language_info(code)['name_local'])
        for code, _name in settings.LANGUAGES
    ]


class PreferencesForm(ModelForm):
    language = ChoiceField(
        label=_('Language'), required=False, choices=_language_choices
    )

    class Meta:
        model = UserProfile
        fields = ('language', 'fold_lines')
        labels = {'fold_lines': _('Fold long entries')}
        help_texts = {
            'fold_lines': _(
                'Lines of an entry the timeline shows before "Show more". '
                '0 never folds. Empty uses the site default.'
            )
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        fold_lines = self.fields['fold_lines']
        fold_lines.widget.attrs.update(
            {'min': 0, 'placeholder': str(settings.FOLD_LINES)}
        )
