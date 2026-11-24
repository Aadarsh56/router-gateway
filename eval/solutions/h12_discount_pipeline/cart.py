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
