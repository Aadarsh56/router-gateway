from register import create_profile
def test_valid_age():
    assert create_profile("Alice", 25) == {"name": "Alice", "age": 25}
def test_valid_zero():
    assert create_profile("Bob", 0) == {"name": "Bob", "age": 0}
def test_invalid_negative():
    assert create_profile("Charlie", -1) is None
def test_invalid_too_old():
    assert create_profile("Dave", 150) is None
def test_valid_max():
    assert create_profile("Eve", 120) == {"name": "Eve", "age": 120}
