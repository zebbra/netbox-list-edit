import logging
from types import SimpleNamespace

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import router, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from mptt.models import MPTTModel

from core.models import ObjectType
from core.signals import clear_events
from extras.choices import CustomFieldTypeChoices
from netbox.registry import registry
from netbox.views.generic.base import BaseMultiObjectView
from utilities.exceptions import AbortRequest, PermissionsViolation
from utilities.permissions import get_permission_for_model
from utilities.views import GetReturnURLMixin

from .forms import build_form
from .ops import apply_list_edit
from .utils import get_list_custom_fields

__all__ = ('BulkListEditView',)

logger = logging.getLogger('netbox_list_edit')


class BulkListEditView(GetReturnURLMixin, BaseMultiObjectView):
    """
    Add, remove or replace single values of a multi-select or multi-object custom field on a set of
    objects, with a preview of the resulting changes.
    """
    template_name = 'netbox_list_edit/bulk_list_edit.html'

    def get_queryset(self, request):
        try:
            object_type = ObjectType.objects.get_by_natural_key(self.kwargs['app_label'], self.kwargs['model_name'])
        except ObjectType.DoesNotExist:
            raise Http404
        self.model = object_type.model_class()
        if self.model is None:
            raise Http404
        self.custom_fields = list(get_list_custom_fields(self.model))
        if not self.custom_fields:
            raise Http404
        return self.model.objects.all()

    def get_required_permission(self):
        return get_permission_for_model(self.model, 'change')

    def get(self, request, **kwargs):
        return redirect(self.get_return_url(request))

    def _get_pk_list(self, request):
        # "Select all N matching query": the list view's filter parameters are passed in the query string
        if request.POST.get('_all'):
            queryset = self.queryset.values_list('pk', flat=True)
            if filterset := registry['filtersets'].get(self.model._meta.label_lower):
                queryset = filterset(request.GET, queryset, request=request).qs
            return list(queryset)
        return [pk for pk in request.POST.getlist('pk') if pk.isdigit()]

    def _get_custom_field(self, name):
        for cf in self.custom_fields:
            if cf.name == name:
                return cf
        return self.custom_fields[0]

    def _labels(self, cf, values):
        """
        Map stored values to (label, url) for display.
        """
        if cf.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            related = cf.related_object_type.model_class().objects.filter(pk__in=values)
            labels = {obj.pk: (str(obj), obj.get_absolute_url()) for obj in related}
            return {v: labels.get(v, (_('#{pk} (deleted)').format(pk=v), None)) for v in values}
        choices = dict(cf.choice_set.choices) if cf.choice_set else {}
        return {v: (choices.get(v, v), None) for v in values}

    def _compute_changes(self, form, objects):
        cf = form.custom_field
        remove = form.values('remove')
        add = form.values('add')
        replace = form.cleaned_data['replace']

        changes = []
        for obj in objects:
            old = obj.custom_field_data.get(cf.name) or []
            new = apply_list_edit(old, remove, add, replace)
            if new != old:
                changes.append(SimpleNamespace(obj=obj, old=old, new=new))
        return changes

    def _preview_rows(self, cf, changes):
        values = {v for c in changes for v in (*c.old, *c.new)}
        labels = self._labels(cf, values)
        rows = []
        for c in changes:
            old_set, new_set = set(c.old), set(c.new)
            rows.append({
                'object': c.obj,
                'old': [(*labels[v], v not in new_set) for v in c.old],
                'new': [(*labels[v], v not in old_set) for v in c.new],
            })
        return rows

    def _save(self, form, changes):
        cf = form.custom_field
        changelog_message = form.cleaned_data.get('changelog_message', '')
        for change in changes:
            obj = change.obj
            if hasattr(obj, 'snapshot'):
                obj.snapshot()
            obj.custom_field_data[cf.name] = change.new or None
            try:
                obj.full_clean()
            except ValidationError as e:
                raise AbortRequest(_('{object}: {error}').format(object=obj, error='; '.join(e.messages)))
            obj._changelog_message = changelog_message
            obj.save()

    def post(self, request, **kwargs):
        pk_list = self._get_pk_list(request)
        # Objects the user may not change are dropped here (self.queryset is permission-restricted)
        selected_objects = self.queryset.filter(pk__in=pk_list)
        selected_pks = list(selected_objects.values_list('pk', flat=True))
        cf = self._get_custom_field(request.POST.get('field'))

        present_values = []
        if cf.type == CustomFieldTypeChoices.TYPE_MULTISELECT:
            seen = set()
            for values in selected_objects.values_list(f'custom_field_data__{cf.name}', flat=True):
                for v in values or []:
                    if v not in seen:
                        seen.add(v)
                        present_values.append(v)
        form_class = build_form(self.model, self.custom_fields, cf, present_values)

        submitted = '_preview' in request.POST or '_apply' in request.POST
        initial = {'field': cf.name, 'loaded_field': cf.name}
        if submitted and request.POST.get('loaded_field') == cf.name:
            form = form_class(request.POST, initial=initial)
        else:
            # First visit, or the user switched to another field: start with empty values
            form = form_class(initial=initial)

        preview = None
        if form.is_bound and form.is_valid():
            changes = self._compute_changes(form, selected_objects)

            if '_apply' in request.POST:
                try:
                    with transaction.atomic(using=router.db_for_write(self.model)):
                        if issubclass(self.model, MPTTModel):
                            with self.model.objects.delay_mptt_updates():
                                self._save(form, changes)
                        else:
                            self._save(form, changes)

                        # Enforce constrained permissions
                        changed_pks = [c.obj.pk for c in changes]
                        if self.queryset.filter(pk__in=changed_pks).count() != len(changed_pks):
                            raise PermissionsViolation

                    messages.success(request, _('Updated {field} on {count} {object_type}').format(
                        field=cf,
                        count=len(changes),
                        object_type=(
                            self.model._meta.verbose_name if len(changes) == 1
                            else self.model._meta.verbose_name_plural
                        ),
                    ))
                    return redirect(self.get_return_url(request))

                except (AbortRequest, PermissionsViolation) as e:
                    logger.debug(e.message)
                    form.add_error(None, e.message)
                    clear_events.send(sender=self)

            preview = self._preview_rows(cf, changes)

        return render(request, self.template_name, {
            'model': self.model,
            'form': form,
            'custom_field': cf,
            'selected_pks': selected_pks,
            'selected_count': len(selected_pks),
            'skipped_count': len(set(map(str, pk_list))) - len(selected_pks),
            'preview': preview,
            'return_url': self.get_return_url(request),
        })
