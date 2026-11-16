import importlib.util
from pathlib import Path

# Load ops.py directly so the tests run without NetBox installed
_spec = importlib.util.spec_from_file_location(
    'ops', Path(__file__).parent.parent / 'netbox_list_edit' / 'ops.py'
)
ops = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ops)
apply = ops.apply_list_edit


def test_add_appends_missing_values():
    assert apply(['a', 'b'], add=['c', 'a']) == ['a', 'b', 'c']


def test_add_to_empty_and_none():
    assert apply(None, add=['a']) == ['a']
    assert apply([], add=['a', 'a']) == ['a']


def test_remove():
    assert apply(['a', 'b', 'c'], remove=['b']) == ['a', 'c']
    assert apply(['a'], remove=['a']) == []


def test_remove_absent_value_is_noop():
    assert apply(['a', 'b'], remove=['x']) == ['a', 'b']


def test_remove_runs_before_add():
    # Removing and adding the same value leaves it present (appended at the end)
    assert apply(['a', 'b'], remove=['a'], add=['a']) == ['b', 'a']


def test_replace_keeps_position():
    assert apply(['a', 'old', 'c'], remove=['old'], add=['new'], replace=True) == ['a', 'new', 'c']


def test_replace_skips_objects_without_old_value():
    assert apply(['a', 'c'], remove=['old'], add=['new'], replace=True) == ['a', 'c']
    assert apply(None, remove=['old'], add=['new'], replace=True) == []


def test_replace_when_new_already_present():
    assert apply(['new', 'old'], remove=['old'], add=['new'], replace=True) == ['new']


def test_replace_multiple_old_values():
    assert apply(['x', 'o1', 'y', 'o2'], remove=['o1', 'o2'], add=['n'], replace=True) == ['x', 'n', 'y']


def test_integers():
    assert apply([1, 2, 3], remove=[2], add=[4]) == [1, 3, 4]
