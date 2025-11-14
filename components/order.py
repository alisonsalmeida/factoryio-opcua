from typing import Tuple, Callable, TypeAlias
from components.base import BoxType
from enum import Enum, auto


class CoverType(Enum):
	WITH_COVER = auto()
	NO_COVER = auto()


class OrderState(Enum):
	WAIT = auto()
	PRODUCTION = auto()
	STORAGE = auto()
	WITHDRAWAL = auto()
	DELIVERY = auto()


class Order:
	def __init__(self, order_id: int, box_type: BoxType, quantity: int, cover: CoverType, delivery: bool):
		self.order_id = order_id
		self.box_type = box_type
		self.quantity = quantity
		self.cover = cover
		self.delivery = delivery
		self.state = OrderState.WAIT
		self.num_storage = None

	def __repr__(self):
		return f"Order(id={self.order_id}, product_type='{self.box_type}', quantity={self.quantity}, state='{self.state}', delivery='{self.delivery}')"


MoveCallbackFn: TypeAlias = Callable[[bool], None]
OrderFn: TypeAlias = Tuple[Order, MoveCallbackFn]
