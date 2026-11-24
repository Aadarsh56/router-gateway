from cart import Cart
from pricing import apply_discount

def checkout_total(cart):
    return cart.subtotal()
