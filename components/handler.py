from components.base import BaseComponent
from asyncua import ua


class Handler(BaseComponent):
    def __init__(self, name, server, namespace_index, base_node):
        super().__init__(name, server, namespace_index, base_node)

        self.num_sensors_rack = 9
        self.sensors_rack = []

    async def run(self):
        pass

    async def build(self):
        # cria os sensores das prateleiras
        name = 'IO: Sensor X'
        idx = self.namespace_index

        for i in range(self.num_sensors_rack):
            node = await self.base_node.add_variable(idx, name + f'{i + 1} {self.name}', False, ua.VariantType.Boolean)
            await node.set_writable(True)
            self.sensors_rack.append(node)

        # sensores de movimento
        self.sensor_x = await self.base_node.add_variable(idx, f'IO:Sensor X {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_x.set_writable(True)

        self.sensor_z = await self.base_node.add_variable(idx, f'IO:Sensor Z {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_z.set_writable(True)

        self.sensor_meio = await self.base_node.add_variable(idx, f'IO:Sensor Meio {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_meio.set_writable(True)

        self.sensor_left = await self.base_node.add_variable(idx, f'IO:Sensor Left {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_left.set_writable(True)

        self.sensor_right = await self.base_node.add_variable(idx, f'IO:Sensor Right {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_right.set_writable(True)

        # movimento
        self.handler_raise = await self.base_node.add_variable(idx, f'IO:Move Raise {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.handler_raise.set_writable(True)
        self.nodes.append(self.handler_raise)

        self.handler_move_leff = await self.base_node.add_variable(idx, f'IO:Mode Left {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.handler_move_leff.set_writable(True)
        self.nodes.append(self.handler_move_leff)

        self.handler_move_right = await self.base_node.add_variable(idx, f'IO:Mode Right {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.handler_move_right.set_writable(True)
        self.nodes.append(self.handler_move_right)

        self.position = await self.base_node.add_variable(idx, f'IO:Position {self.name}', 21474, varianttype=ua.VariantType.Int16)
        await self.position.set_writable(True)
        self.nodes.append(self.position)
