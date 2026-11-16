from extras.choices import CustomFieldTypeChoices, CustomFieldUIEditableChoices
from extras.models import CustomField

__all__ = ('LIST_CF_TYPES', 'get_list_custom_fields')

LIST_CF_TYPES = (
    CustomFieldTypeChoices.TYPE_MULTISELECT,
    CustomFieldTypeChoices.TYPE_MULTIOBJECT,
)


def get_list_custom_fields(model):
    """
    Return the multi-select and multi-object custom fields of a model which are editable in the UI.
    """
    return CustomField.objects.get_for_model(model).filter(
        type__in=LIST_CF_TYPES,
        ui_editable=CustomFieldUIEditableChoices.YES,
    ).order_by('group_name', 'weight', 'name')
