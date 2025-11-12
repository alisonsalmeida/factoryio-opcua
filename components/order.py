from components.base import BoxType


class Order:
	def __init__(self, order_id: int, box_type: BoxType, quantity: int, delivery: bool = False):
		self.order_id = order_id
		self.box_type = box_type
		self.quantity = quantity
		self.delivery = delivery

	def __repr__(self):
		return f"Order(id={self.order_id}, product_type='{self.box_type}', quantity={self.quantity})"