from aggregator import safe_average
def test_normal():    assert safe_average([1, 2, 3, 4]) == 2.5
def test_single():    assert safe_average([10])          == 10.0
def test_empty():     assert safe_average([])            == 0.0
def test_all_same():  assert safe_average([5, 5, 5])    == 5.0
