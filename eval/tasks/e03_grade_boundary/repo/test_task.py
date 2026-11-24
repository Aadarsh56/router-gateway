from grader import is_passing
def test_clearly_passing():  assert is_passing(80) is True
def test_clearly_failing():  assert is_passing(30) is False
def test_boundary_50():      assert is_passing(50) is True
def test_just_below():       assert is_passing(49) is False
def test_just_above():       assert is_passing(51) is True
