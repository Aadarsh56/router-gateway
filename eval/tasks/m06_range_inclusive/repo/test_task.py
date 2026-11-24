from counter import count_up_to
def test_count_to_5():    assert count_up_to(5) == [0, 1, 2, 3, 4, 5]
def test_count_to_1():    assert count_up_to(1) == [0, 1]
def test_count_to_0():    assert count_up_to(0) == [0]
def test_last_element():  assert count_up_to(10)[-1] == 10
