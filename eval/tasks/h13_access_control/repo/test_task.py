from access import can_delete, can_view

def test_admin_1_can_delete():    assert can_delete(1)   is True
def test_admin_2_can_delete():    assert can_delete(2)   is True
def test_admin_3_can_delete():    assert can_delete(3)   is True
def test_user_cannot_delete():    assert can_delete(99)  is False
def test_user_cannot_delete_2():  assert can_delete(100) is False
def test_anyone_can_view():       assert can_view(1)     is True
def test_anyone_can_view_2():     assert can_view(99)    is True
