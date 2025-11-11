from components.base import BaseComponent
from asyncua import ua

import asyncio


class ArmComponent(BaseComponent):
    def __init__(self, name, server, namespace_index, base_node):
        super().__init__(name, server, namespace_index, base_node)

    async def build(self):
        # criar as motores de movimento e direção
        idx = self.namespace_index
        self.move = await self.base_node.add_variable(idx, f'IO:Move {self.name}', False, varianttype=ua.VariantType.Boolean)
        self.move.set_writable(True)

        self.move_front = await self.base_node.add_variable(idx, f'IO:Move Front {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_front.set_writable(True)

        self.move_front = await self.base_node.add_variable(idx, f'IO:Move Back {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_front.set_writable(True)

    async def run(self):
        await self.start_event.wait()

        while True:
            await asyncio.sleep(1)
