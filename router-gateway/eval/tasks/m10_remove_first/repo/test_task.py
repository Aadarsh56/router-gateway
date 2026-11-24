from list_utils import remove_first
def test_basic():  assert remove_first([1, 2, 3]) == [2, 3]
def test_two():    assert remove_first([10, 20])  == [20]
def test_single(): assert remove_first([42])      == []
def test_no_mutate():
    orig = [1, 2, 3]
    result = remove_first(orig)
    assert orig == [1, 2, 3]
    assert result == [2, 3]
