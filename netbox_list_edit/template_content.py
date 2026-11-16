from django.urls import reverse

from netbox.plugins import PluginTemplateExtension
from utilities.permissions import get_permission_for_model

from .utils import get_list_custom_fields


class ListEditButton(PluginTemplateExtension):
    """
    Adds an "Edit List Fields" button next to the bulk action buttons of every object list whose
    model has multi-select or multi-object custom fields.
    """
    models = None

    def list_buttons(self):
        model = self.context.get('object')
        request = self.context['request']
        if not hasattr(model, '_meta'):
            return ''
        if not request.user.has_perm(get_permission_for_model(model, 'change')):
            return ''
        if not get_list_custom_fields(model).exists():
            return ''

        url = reverse('plugins:netbox_list_edit:bulk_list_edit', kwargs={
            'app_label': model._meta.app_label,
            'model_name': model._meta.model_name,
        })
        # Filter parameters let "select all N matching query" resolve the same objects as the list
        if request.GET:
            url = f'{url}?{request.GET.urlencode()}'
        return self.render('netbox_list_edit/list_button.html', {'url': url})


template_extensions = [ListEditButton]
