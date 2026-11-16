# Demo data: list custom fields on devices and locations. Rerunning resets the values.
from core.models import ObjectType
from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, Site
from extras.models import CustomField, CustomFieldChoiceSet

device_ot = ObjectType.objects.get_for_model(Device)
location_ot = ObjectType.objects.get_for_model(Location)
site_ot = ObjectType.objects.get_for_model(Site)

choice_set, _ = CustomFieldChoiceSet.objects.update_or_create(
    name='Monitoring modules',
    defaults={'extra_choices': [
        ['if_mib', 'IF-MIB'],
        ['cisco_cpu', 'Cisco CPU'],
        ['cisco_rf', 'Cisco RF'],
        ['cisco_sdwan', 'Cisco SD-WAN'],
        ['cisco_envmon', 'Cisco EnvMon'],
        ['cisco_envmon_v2', 'Cisco EnvMon v2'],
    ]},
)

modules, _ = CustomField.objects.update_or_create(
    name='monitoring_modules',
    defaults={'type': 'multiselect', 'label': 'Monitoring modules', 'choice_set': choice_set},
)
modules.object_types.set([device_ot, location_ot])

service_group, _ = CustomField.objects.update_or_create(
    name='service_group',
    defaults={'type': 'text', 'label': 'Service group'},
)
service_group.object_types.set([device_ot, location_ot])

backup_sites, _ = CustomField.objects.update_or_create(
    name='backup_sites',
    defaults={'type': 'multiobject', 'label': 'Backup sites', 'related_object_type': site_ot},
)
backup_sites.object_types.set([device_ot, location_ot])

sites = [
    Site.objects.get_or_create(name=name, defaults={'slug': name.lower()})[0]
    for name in ('Zurich', 'Bern', 'Basel', 'Geneva')
]
manufacturer = Manufacturer.objects.get_or_create(name='Cisco', defaults={'slug': 'cisco'})[0]
c3650 = DeviceType.objects.get_or_create(
    manufacturer=manufacturer, model='Catalyst 3650', defaults={'slug': 'catalyst-3650'}
)[0]
c8300 = DeviceType.objects.get_or_create(
    manufacturer=manufacturer, model='C8300', defaults={'slug': 'c8300'}
)[0]
role = DeviceRole.objects.get_or_create(name='Switch', defaults={'slug': 'switch'})[0]
router = DeviceRole.objects.get_or_create(name='Router', defaults={'slug': 'router'})[0]

devices = [
    ('sw-zrh-01', c3650, role, ['if_mib', 'cisco_rf', 'cisco_envmon'], '', [1]),
    ('sw-zrh-02', c3650, role, ['if_mib', 'cisco_rf'], '', []),
    ('sw-brn-01', c3650, role, ['cisco_rf', 'if_mib'], '', [0, 2]),
    ('sw-bsl-01', c3650, role, ['if_mib'], '', []),
    ('rt-zrh-01', c8300, router, ['if_mib', 'cisco_cpu', 'cisco_envmon'], 'sdwan', [1]),
    ('rt-gva-01', c8300, router, ['if_mib'], 'sdwan', []),
    ('rt-brn-01', c8300, router, [], 'internet', []),
]
for name, dtype, drole, mods, group, backups in devices:
    site = sites[0] if 'zrh' in name else sites[1] if 'brn' in name else sites[2] if 'bsl' in name else sites[3]
    device = Device.objects.get_or_create(
        name=name, defaults={'device_type': dtype, 'role': drole, 'site': site}
    )[0]
    device.custom_field_data.update({
        'monitoring_modules': mods or None,
        'service_group': group or None,
        'backup_sites': [sites[i].pk for i in backups] or None,
    })
    device.save()

for site in sites:
    for floor, mods in (('Floor 1', ['if_mib', 'cisco_envmon']), ('Floor 2', ['cisco_rf'])):
        location = Location.objects.get_or_create(
            site=site, name=f'{site.name} {floor}', defaults={'slug': f'{site.slug}-{floor[-1]}'}
        )[0]
        location.custom_field_data.update({'monitoring_modules': mods, 'backup_sites': None})
        location.save()

print('seeded')
