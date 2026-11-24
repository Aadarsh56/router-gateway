#!/usr/bin/env python3
"""
Generate the 15-task eval suite for the Router + Cascade Gateway experiment.
5 easy  |  6 medium  |  4 hard
Each task: buggy repo + instruction + reference solution (never shown to agent)
"""
import pathlib, textwrap, sys

ROOT = pathlib.Path(r"a:\BROWERS DOWNLOAD\eval")
T = ROOT / "tasks"
S = ROOT / "solutions"

def w(rel_path, content):
    p = ROOT / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")

print("Generating 15 eval tasks...")

# ═══════════════════════════════════════════════════════════
# EASY TASKS (5) — single wrong operator / variable / sign
# ═══════════════════════════════════════════════════════════

# E01 — wrong operator (- instead of +)
w("tasks/e01_add_operator/repo/math_ops.py", """
    def add(a, b):
        return a - b
""")
w("tasks/e01_add_operator/repo/test_task.py", """
    from math_ops import add
    def test_add_positive():   assert add(2, 3)    == 5
    def test_add_zero():       assert add(0, 5)    == 5
    def test_add_negative():   assert add(-1, -1)  == -2
    def test_add_large():      assert add(100, 200) == 300
""")
w("tasks/e01_add_operator/instruction.txt", """
    The add function returns wrong results.
    add(2, 3) gives -1 instead of 5.
    add(10, 5) gives 5 instead of 15.
    Fix the add function so it correctly adds two numbers.
""")
w("tasks/e01_add_operator/difficulty.txt", "easy")
w("solutions/e01_add_operator/math_ops.py", """
    def add(a, b):
        return a + b
""")

# E02 — no doubling (returns x instead of x*2)
w("tasks/e02_double_value/repo/number_utils.py", """
    def double(x):
        return x
""")
w("tasks/e02_double_value/repo/test_task.py", """
    from number_utils import double
    def test_double_positive(): assert double(4)    == 8
    def test_double_zero():     assert double(0)    == 0
    def test_double_negative(): assert double(-3)   == -6
    def test_double_float():    assert double(2.5)  == 5.0
""")
w("tasks/e02_double_value/instruction.txt", """
    The double function does not double its input.
    double(4) returns 4 instead of 8.
    double(10) returns 10 instead of 20.
    Fix the function so it returns twice the input value.
""")
w("tasks/e02_double_value/difficulty.txt", "easy")
w("solutions/e02_double_value/number_utils.py", """
    def double(x):
        return x * 2
""")

# E03 — wrong boundary (> instead of >=)
w("tasks/e03_grade_boundary/repo/grader.py", """
    def is_passing(score):
        return score > 50
""")
w("tasks/e03_grade_boundary/repo/test_task.py", """
    from grader import is_passing
    def test_clearly_passing():  assert is_passing(80) is True
    def test_clearly_failing():  assert is_passing(30) is False
    def test_boundary_50():      assert is_passing(50) is True
    def test_just_below():       assert is_passing(49) is False
    def test_just_above():       assert is_passing(51) is True
""")
w("tasks/e03_grade_boundary/instruction.txt", """
    A student who scores exactly 50 should pass, but the function marks them as failing.
    is_passing(50) returns False but should return True.
    is_passing(80) and is_passing(51) are correct.
    Fix the boundary condition.
""")
w("tasks/e03_grade_boundary/difficulty.txt", "easy")
w("solutions/e03_grade_boundary/grader.py", """
    def is_passing(score):
        return score >= 50
""")

# E04 — negated result (-(formula) instead of formula)
w("tasks/e04_celsius_sign/repo/temperature.py", """
    def celsius_to_fahrenheit(c):
        return -(c * 9 / 5 + 32)
""")
w("tasks/e04_celsius_sign/repo/test_task.py", """
    from temperature import celsius_to_fahrenheit
    def test_freezing():   assert celsius_to_fahrenheit(0)   == 32
    def test_boiling():    assert celsius_to_fahrenheit(100) == 212
    def test_body_temp():  assert abs(celsius_to_fahrenheit(37) - 98.6) < 0.1
    def test_below_zero(): assert celsius_to_fahrenheit(-40) == -40
""")
w("tasks/e04_celsius_sign/instruction.txt", """
    The temperature conversion function returns values with the wrong sign.
    celsius_to_fahrenheit(0) returns -32 instead of 32.
    celsius_to_fahrenheit(100) returns -212 instead of 212.
    Every result has the wrong sign. Fix the formula.
""")
w("tasks/e04_celsius_sign/difficulty.txt", "easy")
w("solutions/e04_celsius_sign/temperature.py", """
    def celsius_to_fahrenheit(c):
        return c * 9 / 5 + 32
""")

# E05 — wrong split index ([0] instead of [1])
w("tasks/e05_email_domain/repo/email_utils.py", """
    def get_domain(email):
        return email.split("@")[0]
""")
w("tasks/e05_email_domain/repo/test_task.py", """
    from email_utils import get_domain
    def test_basic():     assert get_domain("user@example.com")     == "example.com"
    def test_subdomain(): assert get_domain("me@mail.company.org")  == "mail.company.org"
    def test_different(): assert get_domain("admin@test.io")         == "test.io"
""")
w("tasks/e05_email_domain/instruction.txt", """
    get_domain("user@example.com") returns "user" instead of "example.com".
    The function is returning the part before the @ symbol instead of the part after it.
    Fix it to return the domain portion of the email address.
""")
w("tasks/e05_email_domain/difficulty.txt", "easy")
w("solutions/e05_email_domain/email_utils.py", """
    def get_domain(email):
        return email.split("@")[1]
""")

# ═══════════════════════════════════════════════════════════
# MEDIUM TASKS (6) — off-by-one, missing edge case, 2-func bug
# ═══════════════════════════════════════════════════════════

# M06 — range off-by-one (range(n) excludes n)
w("tasks/m06_range_inclusive/repo/counter.py", """
    def count_up_to(n):
        return list(range(n))
""")
w("tasks/m06_range_inclusive/repo/test_task.py", """
    from counter import count_up_to
    def test_count_to_5():    assert count_up_to(5) == [0, 1, 2, 3, 4, 5]
    def test_count_to_1():    assert count_up_to(1) == [0, 1]
    def test_count_to_0():    assert count_up_to(0) == [0]
    def test_last_element():  assert count_up_to(10)[-1] == 10
""")
w("tasks/m06_range_inclusive/instruction.txt", """
    count_up_to(5) returns [0, 1, 2, 3, 4] but should return [0, 1, 2, 3, 4, 5].
    The last number (n itself) is always missing from the result.
    The function should count from 0 up to and including n.
""")
w("tasks/m06_range_inclusive/difficulty.txt", "medium")
w("solutions/m06_range_inclusive/counter.py", """
    def count_up_to(n):
        return list(range(n + 1))
""")

# M07 — missing None guard (crashes on None)
w("tasks/m07_none_guard/repo/text_utils.py", """
    def word_count(text):
        return len(text.split())
""")
w("tasks/m07_none_guard/repo/test_task.py", """
    from text_utils import word_count
    def test_normal():      assert word_count("hello world") == 2
    def test_single():      assert word_count("hello")       == 1
    def test_empty():       assert word_count("")             == 0
    def test_none_input():  assert word_count(None)          == 0
    def test_whitespace():  assert word_count("   ")         == 0
""")
w("tasks/m07_none_guard/instruction.txt", """
    word_count(None) raises an AttributeError instead of returning 0.
    The function works correctly for strings but crashes when given None.
    It should return 0 for None input (treating it like an empty text).
""")
w("tasks/m07_none_guard/difficulty.txt", "medium")
w("solutions/m07_none_guard/text_utils.py", """
    def word_count(text):
        if text is None:
            return 0
        return len(text.split())
""")

# M08 — median picks wrong middle index (n//2-1 instead of n//2)
w("tasks/m08_median_index/repo/stats.py", """
    def get_median(numbers):
        if not numbers:
            return None
        sorted_nums = sorted(numbers)
        n = len(sorted_nums)
        return sorted_nums[n // 2 - 1]
""")
w("tasks/m08_median_index/repo/test_task.py", """
    from stats import get_median
    def test_five():      assert get_median([1, 2, 3, 4, 5]) == 3
    def test_single():    assert get_median([7])              == 7
    def test_three():     assert get_median([10, 20, 30])     == 20
    def test_unsorted():  assert get_median([5, 1, 3])        == 3
    def test_empty():     assert get_median([]) is None
""")
w("tasks/m08_median_index/instruction.txt", """
    get_median([1, 2, 3, 4, 5]) returns 2 instead of 3.
    get_median([10, 20, 30]) returns 10 instead of 20.
    The function sorts the list correctly but picks the wrong middle element.
    Fix it so it returns the true middle value for lists with an odd number of elements.
""")
w("tasks/m08_median_index/difficulty.txt", "medium")
w("solutions/m08_median_index/stats.py", """
    def get_median(numbers):
        if not numbers:
            return None
        sorted_nums = sorted(numbers)
        n = len(sorted_nums)
        return sorted_nums[n // 2]
""")

# M09 — missing empty list guard (ZeroDivisionError)
w("tasks/m09_empty_average/repo/aggregator.py", """
    def safe_average(numbers):
        return sum(numbers) / len(numbers)
""")
w("tasks/m09_empty_average/repo/test_task.py", """
    from aggregator import safe_average
    def test_normal():    assert safe_average([1, 2, 3, 4]) == 2.5
    def test_single():    assert safe_average([10])          == 10.0
    def test_empty():     assert safe_average([])            == 0.0
    def test_all_same():  assert safe_average([5, 5, 5])    == 5.0
""")
w("tasks/m09_empty_average/instruction.txt", """
    safe_average([]) raises a ZeroDivisionError instead of returning 0.0.
    The function works correctly for non-empty lists.
    It should return 0.0 when given an empty list instead of crashing.
""")
w("tasks/m09_empty_average/difficulty.txt", "medium")
w("solutions/m09_empty_average/aggregator.py", """
    def safe_average(numbers):
        if not numbers:
            return 0.0
        return sum(numbers) / len(numbers)
""")

# M10 — wrong slice ([:] returns copy instead of [1:])
w("tasks/m10_remove_first/repo/list_utils.py", """
    def remove_first(lst):
        return lst[:]
""")
w("tasks/m10_remove_first/repo/test_task.py", """
    from list_utils import remove_first
    def test_basic():  assert remove_first([1, 2, 3]) == [2, 3]
    def test_two():    assert remove_first([10, 20])  == [20]
    def test_single(): assert remove_first([42])      == []
    def test_no_mutate():
        orig = [1, 2, 3]
        result = remove_first(orig)
        assert orig == [1, 2, 3]
        assert result == [2, 3]
""")
w("tasks/m10_remove_first/instruction.txt", """
    remove_first([1, 2, 3]) returns [1, 2, 3] instead of [2, 3].
    The function should remove the first element and return the rest of the list.
    Currently it returns a full copy of the list with no element removed.
""")
w("tasks/m10_remove_first/difficulty.txt", "medium")
w("solutions/m10_remove_first/list_utils.py", """
    def remove_first(lst):
        return lst[1:]
""")

# M11 — two-function bug: negated condition in caller (not is_valid → is_valid)
w("tasks/m11_two_func_logic/repo/validator.py", """
    def is_valid_age(age):
        return isinstance(age, int) and 0 <= age <= 120
""")
w("tasks/m11_two_func_logic/repo/register.py", """
    from validator import is_valid_age

    def create_profile(name, age):
        if not is_valid_age(age):
            return {"name": name, "age": age}
        return None
""")
w("tasks/m11_two_func_logic/repo/test_task.py", """
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
""")
w("tasks/m11_two_func_logic/instruction.txt", """
    create_profile("Alice", 25) returns None but should return {"name": "Alice", "age": 25}.
    create_profile("Bad", -1) returns a profile dict but should return None.
    Valid ages (0-120) are rejected and invalid ages are accepted.
    The validator.py file is correct. The bug is in how register.py uses the validation result.
""")
w("tasks/m11_two_func_logic/difficulty.txt", "medium")
w("solutions/m11_two_func_logic/validator.py", """
    def is_valid_age(age):
        return isinstance(age, int) and 0 <= age <= 120
""")
w("solutions/m11_two_func_logic/register.py", """
    from validator import is_valid_age

    def create_profile(name, age):
        if is_valid_age(age):
            return {"name": name, "age": age}
        return None
""")

# ═══════════════════════════════════════════════════════════
# HARD TASKS (4) — multi-file, logic, pipeline understanding
# ═══════════════════════════════════════════════════════════

# H12 — 3-file discount pipeline (discount never applied)
w("tasks/h12_discount_pipeline/repo/cart.py", """
    class Cart:
        def __init__(self):
            self.items = []
            self.discount_pct = 0

        def add_item(self, name, price):
            self.items.append({"name": name, "price": price})

        def set_discount(self, pct):
            self.discount_pct = pct

        def subtotal(self):
            return sum(item["price"] for item in self.items)
""")
w("tasks/h12_discount_pipeline/repo/pricing.py", """
    def apply_discount(subtotal, discount_pct):
        return subtotal * (1 - discount_pct / 100)
""")
w("tasks/h12_discount_pipeline/repo/checkout.py", """
    from cart import Cart
    from pricing import apply_discount

    def checkout_total(cart):
        return cart.subtotal()
""")
w("tasks/h12_discount_pipeline/repo/test_task.py", """
    from cart import Cart
    from checkout import checkout_total

    def test_no_discount():
        cart = Cart()
        cart.add_item("apple", 1.00)
        cart.add_item("bread", 2.50)
        assert checkout_total(cart) == 3.50

    def test_20_percent_discount():
        cart = Cart()
        cart.add_item("laptop", 100.00)
        cart.set_discount(20)
        assert checkout_total(cart) == 80.00

    def test_10_percent_discount():
        cart = Cart()
        cart.add_item("book", 50.00)
        cart.add_item("pen", 10.00)
        cart.set_discount(10)
        assert checkout_total(cart) == 54.00

    def test_zero_discount():
        cart = Cart()
        cart.add_item("item", 200.00)
        cart.set_discount(0)
        assert checkout_total(cart) == 200.00
""")
w("tasks/h12_discount_pipeline/instruction.txt", """
    checkout_total() charges the full price even when a discount has been set on the cart.
    A cart with items totalling $100.00 and a 20% discount should cost $80.00,
    but the full $100.00 is always charged regardless of the discount.
    The Cart class has set_discount() and there is a pricing module with apply_discount(),
    but the discount is never being applied at checkout.
    Fix checkout_total() in checkout.py to apply the cart's discount correctly.
""")
w("tasks/h12_discount_pipeline/difficulty.txt", "hard")
w("solutions/h12_discount_pipeline/checkout.py", """
    from cart import Cart
    from pricing import apply_discount

    def checkout_total(cart):
        return apply_discount(cart.subtotal(), cart.discount_pct)
""")
w("solutions/h12_discount_pipeline/cart.py", """
    class Cart:
        def __init__(self):
            self.items = []
            self.discount_pct = 0

        def add_item(self, name, price):
            self.items.append({"name": name, "price": price})

        def set_discount(self, pct):
            self.discount_pct = pct

        def subtotal(self):
            return sum(item["price"] for item in self.items)
""")
w("solutions/h12_discount_pipeline/pricing.py", """
    def apply_discount(subtotal, discount_pct):
        return subtotal * (1 - discount_pct / 100)
""")

# H13 — access control inverted across 2 files
w("tasks/h13_access_control/repo/roles.py", """
    ADMIN_IDS = {1, 2, 3}

    def get_role(user_id):
        return "admin" if user_id in ADMIN_IDS else "user"
""")
w("tasks/h13_access_control/repo/access.py", """
    from roles import get_role

    def can_delete(user_id):
        role = get_role(user_id)
        if role == "admin":
            return False
        return True

    def can_view(user_id):
        return True
""")
w("tasks/h13_access_control/repo/test_task.py", """
    from access import can_delete, can_view

    def test_admin_1_can_delete():    assert can_delete(1)   is True
    def test_admin_2_can_delete():    assert can_delete(2)   is True
    def test_admin_3_can_delete():    assert can_delete(3)   is True
    def test_user_cannot_delete():    assert can_delete(99)  is False
    def test_user_cannot_delete_2():  assert can_delete(100) is False
    def test_anyone_can_view():       assert can_view(1)     is True
    def test_anyone_can_view_2():     assert can_view(99)    is True
""")
w("tasks/h13_access_control/instruction.txt", """
    The access control system has the permissions completely backwards.
    Admin users (IDs 1, 2, 3) are being denied delete access — can_delete() returns False.
    Regular users (all other IDs) are being granted delete access — can_delete() returns True.
    Only admins should be allowed to delete.
    The roles.py file is correct — the bug is in access.py.
    Fix can_delete() so admins return True and regular users return False.
""")
w("tasks/h13_access_control/difficulty.txt", "hard")
w("solutions/h13_access_control/roles.py", """
    ADMIN_IDS = {1, 2, 3}

    def get_role(user_id):
        return "admin" if user_id in ADMIN_IDS else "user"
""")
w("solutions/h13_access_control/access.py", """
    from roles import get_role

    def can_delete(user_id):
        role = get_role(user_id)
        if role == "admin":
            return True
        return False

    def can_view(user_id):
        return True
""")

# H14 — normalize uses wrong reference (x - max instead of x - min)
w("tasks/h14_normalize_bug/repo/data_utils.py", """
    def normalize(values):
        if not values:
            return []
        min_val = min(values)
        max_val = max(values)
        if max_val == min_val:
            return [0.0] * len(values)
        return [(x - max_val) / (max_val - min_val) for x in values]
""")
w("tasks/h14_normalize_bug/repo/pipeline.py", """
    from data_utils import normalize

    def process_dataset(data):
        return normalize(data)
""")
w("tasks/h14_normalize_bug/repo/test_task.py", """
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
""")
w("tasks/h14_normalize_bug/instruction.txt", """
    The normalize function should map values to the [0, 1] range, where the minimum
    value maps to 0.0 and the maximum value maps to 1.0.
    Instead, the minimum maps to a negative number and the maximum maps to 0.0.
    For example, process_dataset([0, 5, 10]) returns [-1.0, -0.5, 0.0] instead of [0.0, 0.5, 1.0].
    The range calculation finds both min and max correctly, but the formula inside
    the list comprehension in data_utils.py has an error. Fix it.
""")
w("tasks/h14_normalize_bug/difficulty.txt", "hard")
w("solutions/h14_normalize_bug/data_utils.py", """
    def normalize(values):
        if not values:
            return []
        min_val = min(values)
        max_val = max(values)
        if max_val == min_val:
            return [0.0] * len(values)
        return [(x - min_val) / (max_val - min_val) for x in values]
""")
w("solutions/h14_normalize_bug/pipeline.py", """
    from data_utils import normalize

    def process_dataset(data):
        return normalize(data)
""")

# H15 — event processing: sorted() destroys order dependency
w("tasks/h15_event_order/repo/processor.py", """
    class EventProcessor:
        def __init__(self):
            self.state = {}

        def handle_create(self, event):
            self.state[event["id"]] = {"value": event["value"], "active": True}

        def handle_update(self, event):
            if event["id"] in self.state and self.state[event["id"]]["active"]:
                self.state[event["id"]]["value"] = event["value"]

        def handle_delete(self, event):
            if event["id"] in self.state:
                self.state[event["id"]]["active"] = False

        def get_active(self):
            return {k: v["value"] for k, v in self.state.items() if v["active"]}
""")
w("tasks/h15_event_order/repo/pipeline.py", """
    from processor import EventProcessor

    def process_events(events):
        proc = EventProcessor()
        for event in sorted(events, key=lambda e: e["type"]):
            getattr(proc, f"handle_{event['type']}")(event)
        return proc.get_active()
""")
w("tasks/h15_event_order/repo/test_task.py", """
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
""")
w("tasks/h15_event_order/instruction.txt", """
    process_events() produces wrong results when events depend on order.
    After creating item "a" and then deleting it, item "a" still appears in the output.
    After creating item "b" with value 10 and then updating it to 20, the value is still 10.
    Events must be processed in the order they arrive — the sequence matters because
    you cannot update an item before it is created, and deleting after updating is different
    from deleting before updating. Fix pipeline.py so events run in their original order.
""")
w("tasks/h15_event_order/difficulty.txt", "hard")
w("solutions/h15_event_order/processor.py", """
    class EventProcessor:
        def __init__(self):
            self.state = {}

        def handle_create(self, event):
            self.state[event["id"]] = {"value": event["value"], "active": True}

        def handle_update(self, event):
            if event["id"] in self.state and self.state[event["id"]]["active"]:
                self.state[event["id"]]["value"] = event["value"]

        def handle_delete(self, event):
            if event["id"] in self.state:
                self.state[event["id"]]["active"] = False

        def get_active(self):
            return {k: v["value"] for k, v in self.state.items() if v["active"]}
""")
w("solutions/h15_event_order/pipeline.py", """
    from processor import EventProcessor

    def process_events(events):
        proc = EventProcessor()
        for event in events:
            getattr(proc, f"handle_{event['type']}")(event)
        return proc.get_active()
""")

# ─── Write task index ─────────────────────────────────────
import json
task_index = []
for td in sorted((T).iterdir()):
    if td.is_dir():
        diff = (td / "difficulty.txt").read_text().strip()
        instr = (td / "instruction.txt").read_text().strip()[:80]
        task_index.append({"name": td.name, "difficulty": diff, "instruction_preview": instr})
(ROOT / "task_index.json").write_text(json.dumps(task_index, indent=2), encoding="utf-8")

print(f"\n✅ Done. {len(task_index)} tasks created.")
print(f"Tasks:     {T}")
print(f"Solutions: {S}")
print(f"Index:     {ROOT / 'task_index.json'}")

# Split: first 5 = tuning set, last 10 = held-out
all_names = [t["name"] for t in task_index]
tuning = all_names[:5]
held_out = all_names[5:]
print(f"\nTuning set  ({len(tuning)}): {tuning}")
print(f"Held-out    ({len(held_out)}): {held_out}")

