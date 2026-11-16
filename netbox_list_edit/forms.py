from django import forms
from django.utils.translation import gettext_lazy as _

from extras.choices import CustomFieldTypeChoices
from netbox.forms.mixins import ChangelogMessageMixin
from netbox.models.features import ChangeLoggingMixin
from utilities.forms.fields import DynamicModelMultipleChoiceField, DynamicMultipleChoiceField
from utilities.forms.widgets import APISelectMultiple

__all__ = ('ListEditFormBase', 'build_form')


class ListEditFormBase(forms.Form):
    field = forms.ChoiceField(
        label=_('Custom field'),
    )
    remove = None
    add = None
    replace = forms.BooleanField(
        label=_('Replace'),
        required=False,
        help_text=_('Add values only to objects that contained a removed value, at its position'),
    )
    # Name of the custom field the value widgets were rendered for; differs from "field" when the
    # user switched fields, so the posted values belong to another field and must be discarded.
    loaded_field = forms.CharField(widget=forms.HiddenInput, required=False)

    custom_field = None

    def clean(self):
        data = super().clean()
        if not data.get('remove') and not data.get('add'):
            raise forms.ValidationError(_('Select at least one value to remove or add.'))
        if data.get('replace') and not (data.get('remove') and data.get('add')):
            raise forms.ValidationError(_('Replace needs values to remove and values to add.'))
        return data

    def values(self, name):
        """
        Return the cleaned values of "remove" or "add" in their stored form (choice values or PKs).
        """
        values = self.cleaned_data.get(name) or []
        if self.custom_field.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            return [obj.pk for obj in values]
        return list(values)


def build_form(model, custom_fields, custom_field, present_values=()):
    """
    Build the form class for the selected custom field.

    present_values: values found on the selected objects; offered for removal even if they are no
        longer part of the field's choice set.
    """
    attrs = {
        'custom_field': custom_field,
    }

    if custom_field.type == CustomFieldTypeChoices.TYPE_MULTISELECT:
        choices = list(custom_field.choice_set.choices)
        known = {value for value, _label in choices}
        stale = [(v, _('{value} (not in choice set)').format(value=v)) for v in present_values if v not in known]
        attrs['remove'] = forms.MultipleChoiceField(
            label=_('Remove'),
            choices=choices + stale,
            required=False,
        )
        attrs['add'] = DynamicMultipleChoiceField(
            label=_('Add'),
            choices=choices,
            required=False,
            widget=APISelectMultiple(
                api_url=f'/api/extras/custom-field-choice-sets/{custom_field.choice_set.pk}/choices/'
            ),
        )
    else:
        related_model = custom_field.related_object_type.model_class()
        attrs['remove'] = DynamicModelMultipleChoiceField(
            label=_('Remove'),
            queryset=related_model.objects.all(),
            required=False,
            selector=True,
        )
        attrs['add'] = DynamicModelMultipleChoiceField(
            label=_('Add'),
            queryset=related_model.objects.all(),
            required=False,
            query_params=custom_field.related_object_filter,
            selector=True,
        )

    bases = (ListEditFormBase,)
    if issubclass(model, ChangeLoggingMixin):
        bases = (ChangelogMessageMixin, ListEditFormBase)
    form_class = type('ListEditForm', bases, attrs)

    class _Form(form_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['field'].choices = [(cf.name, str(cf)) for cf in custom_fields]
            self.fields['field'].widget.attrs['data-list-edit-switch'] = 'true'

    return _Form
