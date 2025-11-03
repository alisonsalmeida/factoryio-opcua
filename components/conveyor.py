from components.base import BaseComponent
from asyncua import ua

import asyncio


class Conveyor(BaseComponent):
    def __init__(self, name, server, namespace_index, base_node, num_engines: int):
        super().__init__(name, server, namespace_index, base_node)
        
        self.num_engines = num_engines
        self.num_sensors = 2
        self.engines = []
        self.sensors = []

    async def build(self):
        idx = self.namespace_index
        name = 'IO: Engine:'
        for i in range(0, self.num_engines):
            node = await self.base_node.add_variable(idx, name + f'{i} {self.name}', False, varianttype=ua.VariantType.Boolean)
            await node.set_writable(True)

            self.engines.append(node)

        # gera os sensores
        names = [f'IO:Sensor Start {self.name}', f'IO:Sensor End {self.name}']
        for i in range(0, self.num_sensors):
            node = await self.base_node.add_variable(self.namespace_index, names[i], False, varianttype=ua.VariantType.Boolean)
            await node.set_writable(True)
            self.sensors.append(node)
    
    async def run(self):
        await self.start_event.wait()

        while True:
            await asyncio.sleep(1)
