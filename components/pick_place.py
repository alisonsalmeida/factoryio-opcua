from components.base import BaseComponent
from asyncua import ua


class PickPlace(BaseComponent):
    def __init__(self, name, server, namespace_index, base_node):
        super().__init__(name, server, namespace_index, base_node)
    
    async def run(self):
        return await super().run()
    
    async def build(self):
        # gera os atuadores
        idx = self.namespace_index
        
        self.move_z = self.base_node.add_variable(idx, f'IO: MoveZ {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_z.set_writable(True)

        self.move_x = self.base_node.add_variable(idx, f'IO: MoveX {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_x.set_writable(True)

        self.move_x_clock = self.base_node.add_variable(idx, f'IO: MoveX Clock {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_x_clock.set_writable(True)

        self.move_x_anticlock = self.base_node.add_variable(idx, f'IO: MoveX AntiClock {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_x_anticlock.set_writable(True)

        self.move_c_clock = self.base_node.add_variable(idx, f'IO: MoveC Clock {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_c_clock.set_writable(True)

        self.move_c_anticlock = self.base_node.add_variable(idx, f'IO: MoveC AntiClock {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.move_c_anticlock.set_writable(True)

        # gera os sensores
        self.moving_z = self.base_node.add_variable(idx, f'IO: MovingZ {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.moving_z.set_writable(True)

        self.moving_x = self.base_node.add_variable(idx, f'IO: MovingX {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.moving_x.set_writable(True)

        