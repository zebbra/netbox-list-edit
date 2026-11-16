# End-to-end checks against the seeded demo, run inside the NetBox container:
#   docker compose exec netbox sh -c '/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell < /demo/smoke.py'
# Resets to the seeded state and runs in a transaction that is rolled back at the end.
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client

from core.models import ObjectChange, ObjectType
from dcim.models import Device, Location, Site
from users.models import ObjectPermission

URL = '/plugins/list-edit/{}/'
User = get_user_model()


class Rollback(Exception):
    pass


def modules(name):
    return Device.objects.get(name=name).custom_field_data.get('monitoring_modules')


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        global failed
        failed = True


failed = False
try:
    with transaction.atomic():
        exec(open('/demo/seed.py').read(), {})  # start from the seeded state
        admin = User.objects.get(username='admin')
        c = Client()
        c.force_login(admin)

        # Buttons: device and location lists have it, site list (no list fields) does not
        r = c.get('/dcim/devices/?device_type=catalyst-3650')
        check(b'list-edit-button' in r.content and b'/plugins/list-edit/dcim/device/?device_type=catalyst-3650' in r.content,
              'device list renders button with filter query')
        check(b'list-edit-button' in c.get('/dcim/locations/').content, 'location list renders button')
        check(b'list-edit-button' not in c.get('/dcim/sites/').content, 'site list has no button')

        # 1. Remove via "select all matching query"
        q = '?device_type=catalyst-3650&cf_monitoring_modules=cisco_rf'
        base = {'_all': 'on', 'return_url': '/dcim/devices/'}
        r = c.post(URL.format('dcim/device') + q, base)
        check(r.status_code == 200 and b'Edit List Fields' in r.content, 'form opens for all matching')
        pks = list(Device.objects.filter(device_type__slug='catalyst-3650',
                                         custom_field_data__monitoring_modules__contains='cisco_rf').values_list('pk', flat=True))
        data = {'pk': pks, 'field': 'monitoring_modules', 'loaded_field': 'monitoring_modules',
                'remove': ['cisco_rf'], 'return_url': '/dcim/devices/', 'changelog_message': 'drop rf'}
        r = c.post(URL.format('dcim/device'), {**data, '_preview': ''})
        check(b'3 of 3 objects change' in r.content, 'remove preview: 3 of 3 change')
        r = c.post(URL.format('dcim/device'), {**data, '_apply': ''})
        check(r.status_code == 302, 'remove applied')
        check(modules('sw-zrh-01') == ['if_mib', 'cisco_envmon'] and modules('sw-zrh-02') == ['if_mib']
              and modules('sw-brn-01') == ['if_mib'], 'cisco_rf removed, order kept')
        oc = ObjectChange.objects.filter(changed_object_id=Device.objects.get(name='sw-zrh-01').pk).first()
        check(oc and oc.message == 'drop rf' and oc.user == admin, 'changelog entry with message')

        # 2. Replace on all devices: only those with the old value change, at the same position
        all_pks = list(Device.objects.values_list('pk', flat=True))
        data = {'pk': all_pks, 'field': 'monitoring_modules', 'loaded_field': 'monitoring_modules',
                'remove': ['cisco_envmon'], 'add': ['cisco_envmon_v2'], 'replace': 'on'}
        r = c.post(URL.format('dcim/device'), {**data, '_preview': ''})
        check(b'2 of 7 objects change' in r.content, 'replace preview: 2 of 7 change')
        c.post(URL.format('dcim/device'), {**data, '_apply': ''})
        check(modules('sw-zrh-01') == ['if_mib', 'cisco_envmon_v2']
              and modules('rt-zrh-01') == ['if_mib', 'cisco_cpu', 'cisco_envmon_v2']
              and modules('sw-bsl-01') == ['if_mib'], 'replace in place, others untouched')

        # 3. Add via filter on another custom field
        r = c.post(URL.format('dcim/device') + '?cf_service_group=sdwan', {'_all': 'on'})
        sd = list(Device.objects.filter(custom_field_data__service_group='sdwan').values_list('pk', flat=True))
        data = {'pk': sd, 'field': 'monitoring_modules', 'loaded_field': 'monitoring_modules', 'add': ['cisco_sdwan']}
        c.post(URL.format('dcim/device'), {**data, '_apply': ''})
        check(modules('rt-gva-01') == ['if_mib', 'cisco_sdwan'] and modules('rt-brn-01') is None, 'add to sdwan only')

        # 4. Second model, multi-object field: add and remove sites on locations
        locs = list(Location.objects.filter(name__endswith='Floor 2').values_list('pk', flat=True))
        geneva, bern = Site.objects.get(name='Geneva'), Site.objects.get(name='Bern')
        data = {'pk': locs, 'field': 'backup_sites', 'loaded_field': 'backup_sites', 'add': [geneva.pk, bern.pk]}
        r = c.post(URL.format('dcim/location'), {**data, '_preview': ''})
        check(b'4 of 4 objects change' in r.content, 'location multiobject preview')
        c.post(URL.format('dcim/location'), {**data, '_apply': ''})
        data = {'pk': locs, 'field': 'backup_sites', 'loaded_field': 'backup_sites', 'remove': [bern.pk]}
        c.post(URL.format('dcim/location'), {**data, '_apply': ''})
        check(all(l.custom_field_data['backup_sites'] == [geneva.pk] for l in Location.objects.filter(pk__in=locs)),
              'location backup_sites == [Geneva]')

        # Removing the last value stores null, like clearing in bulk edit
        data = {'pk': locs, 'field': 'backup_sites', 'loaded_field': 'backup_sites', 'remove': [geneva.pk]}
        c.post(URL.format('dcim/location'), {**data, '_apply': ''})
        check(all(l.custom_field_data['backup_sites'] is None for l in Location.objects.filter(pk__in=locs)),
              'empty list stored as null')

        # Switching the field discards values posted for the previous one
        r = c.post(URL.format('dcim/device'), {'pk': all_pks, 'field': 'backup_sites',
                                                'loaded_field': 'monitoring_modules', 'remove': ['if_mib'], '_preview': ''})
        check(b'objects change' not in r.content and r.status_code == 200, 'field switch re-renders without preview')

        # Validation
        r = c.post(URL.format('dcim/device'), {'pk': all_pks, 'field': 'monitoring_modules',
                                                'loaded_field': 'monitoring_modules', '_preview': ''})
        check(b'Select at least one value' in r.content, 'empty submission rejected')

        # Unknown model / model without list fields
        check(c.post(URL.format('dcim/site'), {}).status_code == 404, 'site (no list fields) 404')
        check(c.post(URL.format('dcim/nonsense'), {}).status_code == 404, 'unknown model 404')

        # Permissions: view-only user gets 403; constrained change permission limits objects
        viewer = User.objects.create_user('viewer', password='x')
        perm = ObjectPermission.objects.create(name='view devices', actions=['view'])
        perm.object_types.add(ObjectType.objects.get_for_model(Device))
        perm.users.add(viewer)
        cv = Client()
        cv.force_login(viewer)
        check(b'list-edit-button' not in cv.get('/dcim/devices/').content, 'no button without change permission')
        check(cv.post(URL.format('dcim/device'), {'pk': all_pks}).status_code == 403, '403 without change permission')

        perm2 = ObjectPermission.objects.create(name='change zrh', actions=['change'],
                                                constraints={'site__name': 'Zurich'})
        perm2.object_types.add(ObjectType.objects.get_for_model(Device))
        perm2.users.add(viewer)
        data = {'pk': all_pks, 'field': 'monitoring_modules', 'loaded_field': 'monitoring_modules', 'add': ['cisco_cpu']}
        r = cv.post(URL.format('dcim/device'), {**data, '_preview': ''})
        check(b'of 3 objects change' in r.content, 'constrained user only sees permitted objects')
        check(b'4 selected objects are skipped' in r.content, 'skipped objects are reported')
        cv.post(URL.format('dcim/device'), {**data, '_apply': ''})
        check('cisco_cpu' not in modules('sw-bsl-01') and 'cisco_cpu' in modules('sw-zrh-02'),
              'constrained apply touches only permitted objects')

        raise Rollback
except Rollback:
    pass

print('FAILED' if failed else 'ALL OK')
