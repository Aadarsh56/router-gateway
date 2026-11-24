from pipeline import process_dataset

def test_basic():
    result = process_dataset([0, 5, 10])
    assert result == [0.0, 0.5, 1.0]

def test_all_same():
    assert process_dataset([3, 3, 3]) == [0.0, 0.0, 0.0]

def test_min_becomes_zero():
    result = process_dataset([2, 4, 6])
    assert result[0] == 0.0

def test_max_becomes_one():
    result = process_dataset([2, 4, 6])
    assert result[-1] == 1.0

def test_empty():
    assert process_dataset([]) == []
