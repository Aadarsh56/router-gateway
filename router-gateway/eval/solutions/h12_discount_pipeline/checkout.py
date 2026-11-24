from cart import Cart
from pricing import apply_discount

def checkout_total(cart):
    return apply_discount(cart.subtotal(), cart.discount_pct)
