"""
Pure list operations, kept free of Django so they can be tested standalone.
"""

__all__ = ('apply_list_edit',)


def apply_list_edit(current, remove=(), add=(), replace=False):
    """
    Return the new list after removing and adding values.

    Removals run before additions. Order is preserved and duplicates are not introduced.

    replace: add values only if at least one removed value was present, and insert them at the
        position of the first removed value (renames keep their place in the list).
    """
    current = list(current or [])
    remove = set(remove)

    kept = []
    insert_at = None
    for value in current:
        if value in remove:
            if insert_at is None:
                insert_at = len(kept)
        else:
            kept.append(value)

    if replace and insert_at is None:
        return current

    additions = []
    for value in add:
        if value not in kept and value not in additions:
            additions.append(value)

    if replace:
        return kept[:insert_at] + additions + kept[insert_at:]
    return kept + additions
