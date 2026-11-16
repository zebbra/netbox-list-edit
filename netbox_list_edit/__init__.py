from netbox.plugins import PluginConfig

__version__ = '0.1.0'


class ListEditConfig(PluginConfig):
    name = 'netbox_list_edit'
    verbose_name = 'List Edit'
    description = 'Add, remove or replace single values of multi-select and multi-object custom fields in bulk'
    version = __version__
    author = 'Stefan Grosser'
    base_url = 'list-edit'
    min_version = '4.4.0'


config = ListEditConfig
