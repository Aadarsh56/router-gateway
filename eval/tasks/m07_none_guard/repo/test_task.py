from text_utils import word_count
def test_normal():      assert word_count("hello world") == 2
def test_single():      assert word_count("hello")       == 1
def test_empty():       assert word_count("")             == 0
def test_none_input():  assert word_count(None)          == 0
def test_whitespace():  assert word_count("   ")         == 0
