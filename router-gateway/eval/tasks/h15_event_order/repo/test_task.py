from pipeline import process_events

def test_create_then_delete():
    events = [
        {"type": "create", "id": "a", "value": 1},
        {"type": "delete", "id": "a"},
    ]
    assert "a" not in process_events(events)

def test_create_then_update():
    events = [
        {"type": "create", "id": "b", "value": 10},
        {"type": "update", "id": "b", "value": 20},
    ]
    assert process_events(events) == {"b": 20}

def test_mixed_sequence():
    events = [
        {"type": "create", "id": "x", "value": 1},
        {"type": "create", "id": "y", "value": 2},
        {"type": "update", "id": "x", "value": 99},
        {"type": "delete", "id": "y"},
    ]
    result = process_events(events)
    assert result == {"x": 99}
    assert "y" not in result

def test_update_before_create():
    events = [
        {"type": "update", "id": "z", "value": 5},
        {"type": "create", "id": "z", "value": 1},
    ]
    assert process_events(events) == {"z": 1}
