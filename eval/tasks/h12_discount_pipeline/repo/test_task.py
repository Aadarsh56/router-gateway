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
