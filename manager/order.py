from typing import Tuple
from asyncua import uamethod, ua
from components.base import BoxType
from components.order import Order, CoverType

import asyncio


class ProcessOrder:
	def __init__(self,
		order_queue_green: asyncio.Queue[Order], 
		order_queue_blue: asyncio.Queue[Order], 
		order_queue_metal: asyncio.Queue[Order]
	):
		self.order_queue_green = order_queue_green
		self.order_queue_blue = order_queue_blue
		self.order_queue_metal = order_queue_metal
		self.order_id = 1
		
	async def handle_new_order(
		self, parent,  box_type: BoxType, quantity: int, cover: bool, delivery: bool) -> Tuple[ua.Variant, ua.Variant]:
		
		# Cria o pedido
		box_type = BoxType(box_type)
		cover_type = CoverType.WITH_COVER if cover else CoverType.NO_COVER
		order: Order = Order(self.order_id, box_type, quantity, cover_type, delivery)
		self.order_id += 1

		# Coloca o pedido na fila para o worker processar
		if box_type == BoxType.GREEN:
			await self.order_queue_green.put(order)
		elif box_type == BoxType.BLUE:
			await self.order_queue_blue.put(order)
		elif box_type == BoxType.METAL:
			await self.order_queue_metal.put(order)

		print(f"[Method] Order received and enqueue: {order}")

		return (
			ua.Variant(True, ua.VariantType.Boolean), 
			ua.Variant(f"Order received for {quantity}x type {box_type.name} received.", ua.VariantType.String)
		)
