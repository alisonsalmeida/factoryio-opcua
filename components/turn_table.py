from typing import Tuple
from components.base import BaseComponent
from components.box_producer import BoxType
from asyncua import ua, Node

import asyncio


class TurnTable(BaseComponent):
    def __init__(self, name, server, namespace_index, base_node, steps: dict, queue: asyncio.Queue[Tuple[BoxType, callable]]):
        super().__init__(name, server, namespace_index, base_node)

        self.steps: dict = steps
        self.queue = queue

    async def build(self):
        # cria os movimentos
        self.node_move_turn = await self.base_node.add_variable(self.namespace_index, f'I0: Rotate {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_move_turn.set_writable(True)

        self.node_roll_plus = await self.base_node.add_variable(self.namespace_index, f'IO: Roll+ {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_plus.set_writable(True)

        self.node_roll_minus = await self.base_node.add_variable(self.namespace_index, f'IO: Roll- {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_minus.set_writable(True)

        # cria os sensores
        self.node_sensor_turn_zero = await self.base_node.add_variable(self.namespace_index, f'IO: Turn0 {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_sensor_turn_zero.set_writable(True)

        self.node_sensor_turn_nineteen = await self.base_node.add_variable(self.namespace_index, f'IO: Turn90 {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_sensor_turn_nineteen.set_writable(True)

        self.node_roll_front_limit = await self.base_node.add_variable(self.namespace_index, f'IO: LimitFront {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_front_limit.set_writable(True)

        self.node_roll_back_limit = await self.base_node.add_variable(self.namespace_index, f'IO: LimitBack {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_back_limit.set_writable(True)

    async def run(self):
        await self.start_event.wait()
        
        while True:
            box_type, callable = await self.queue.get()
            print(f'chegou caixa: {box_type}')
