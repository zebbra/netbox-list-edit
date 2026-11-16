# Draft: NetBox feature request

Fields follow the NetBox "Feature Request" issue template.

**Title:** Enable adding & removing values of multi-select and multi-object custom fields via bulk edit

**NetBox version:** v4.6.5

**Feature type:** Change to existing functionality

### Proposed functionality

Extend the generic bulk edit form with add/remove controls for custom fields of type *multiple selection* and *multiple objects*, analogous to *Add tags* / *Remove tags* and to the contacts section added in #23672:

- For each such custom field, besides today's "set" input and the *Set null* checkbox, offer **Add** and **Remove** inputs (choices from the choice set, or objects of the related type).
- Removals are applied before additions, as in #23672.
- Values already present are not duplicated; the order of remaining values is kept; an empty result is stored as null.
- Optionally, a **Replace** flag: add the new value only to objects that contained a removed value (e.g. renaming a value). This could also be left out of a first version.
- Setting a value and adding/removing for the same field at the same time is rejected as a validation error.

Data model and API stay unchanged; the values remain lists in `custom_field_data`. The REST API already allows read-modify-write per object; this is about the UI bulk edit.

A working implementation exists as a plugin: <link to repo>. It adds a separate view with a preview (old → new per object, similar to bulk rename) and works for all models with custom fields, including plugin models. For core, the add/remove inputs would fit directly into `BulkEditView` / `NetBoxModelBulkEditForm`, like the contacts change in #23672.

### Use case

Multi-select and multi-object custom fields often hold sets: enabled monitoring modules, services, applicable policies, related sites. Typical bulk changes touch one value, not the whole list:

1. **Remove** one value from all objects matching a filter, e.g. drop module `x` from all devices of a device type that have it, leaving their other modules alone.
2. **Replace** a value that was renamed, on every object that has it, without adding it to objects that did not.
3. **Add** a value to all objects matching a filter, e.g. all devices with a given role or custom field value.

Today bulk edit can only overwrite the whole list with the same value on every object. Because the lists differ per object, that destroys data (cf. #7321), so these changes need the API or a script. Tags have add/remove in bulk edit, contacts got it in #23672; list custom fields are the remaining multi-value attribute without it.

### Database changes

None.

### External dependencies

None.
