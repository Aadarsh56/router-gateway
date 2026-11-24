from stats import get_median
def test_five():      assert get_median([1, 2, 3, 4, 5]) == 3
def test_single():    assert get_median([7])              == 7
def test_three():     assert get_median([10, 20, 30])     == 20
def test_unsorted():  assert get_median([5, 1, 3])        == 3
def test_empty():     assert get_median([]) is None
