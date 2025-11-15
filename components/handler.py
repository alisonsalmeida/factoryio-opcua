from components.base import BaseComponent, EventSensorHandle, EdgeDetector, EdgeType
from asyncua import ua
from asyncua.ua import DataValue, Variant, VariantType
from components.order import OrderFn


import asyncio


class Handler(BaseComponent):
    def __init__(self, name, server, namespace_index, base_node,
                 queue_input_a: asyncio.Queue[OrderFn],
                 queue_input_b: asyncio.Queue[OrderFn],
                 sem_input_a: asyncio.Semaphore,
                 sem_input_b: asyncio.Semaphore
        ):
        
        super().__init__(name, server, namespace_index, base_node)

        self.queue_input_a = queue_input_a
        self.queue_input_b = queue_input_b
        self.sem_input_a = sem_input_a
        self.sem_input_b = sem_input_b
        self.num_sensors_rack = 9
        self.sensors_rack = []
        self.positions = {}
        self.idle_position = 21474
        self.lock_processor = asyncio.Lock()
        self._started_moving = asyncio.Event()
        self._stopped_moving = asyncio.Event()
        
        self._stopped_moving.set()
        self._is_moving = False
        self._position = 1

    async def create_edge_detectors(self):
        ev_moving_x = asyncio.Event()
        ev_moving_z = asyncio.Event()
        ev_handler_left = asyncio.Event()
        ev_handler_right = asyncio.Event()
        ev_handler_center = asyncio.Event()

        edge_dectors = []
        self.edge_moving_x = EdgeDetector(self.sensor_x.nodeid, ev_moving_x, EdgeType.FALLING)
        edge_dectors.append(self.edge_moving_x)

        self.edge_moving_z = EdgeDetector(self.sensor_z.nodeid, ev_moving_z, EdgeType.FALLING)
        edge_dectors.append(self.edge_moving_z)

        self.edge_handler_left = EdgeDetector(self.sensor_left.nodeid, ev_handler_left, EdgeType.RISING)
        edge_dectors.append(self.edge_handler_left)

        self.edge_handler_right = EdgeDetector(self.sensor_right.nodeid, ev_handler_right, EdgeType.RISING)
        edge_dectors.append(self.edge_handler_right)

        self.edge_handler_center = EdgeDetector(self.sensor_center.nodeid, ev_handler_center, EdgeType.RISING)
        edge_dectors.append(self.edge_handler_center)

        self.handler = EventSensorHandle(self.server, edge_dectors)
        sub = await self.server.create_subscription(10, self.handler)        
        await sub.subscribe_data_change([self.sensor_x, self.sensor_z, self.sensor_left, self.sensor_right, self.sensor_center])

    async def run(self):
        print('[Handler]: start process task')
        await self.create_edge_detectors()
        await self.start_event.wait()

        asyncio.create_task(self.process_input_a())
        asyncio.create_task(self.process_input_b())
        asyncio.create_task(self.task_monitor_moving())
        
    async def process_input_a(self):
        print(f'[Handler]: awaiting orders in input a to storage')

        while True:

            async with self.sem_input_a:
                task_idle_monitor = asyncio.create_task(self.monitor_idle())
                order, _ = await self.queue_input_a.get()
                print(f'[Handler]: get new order from input a to storage: {order}')

                async with self.lock_processor:
                    # move para posição inicial de A
                    task_idle_monitor.cancel()
                    await self._move_home_a()
                    await self._raise_product()
                    await self._move_product()
                    await self._release_product()
                    await self._move_home_a()
                    # aguarda para pegar o proximo item
                
                await asyncio.sleep(0.5)
    
    async def process_input_b(self):
        while True:
            async with self.sem_input_b:
                task_idle_monitor = asyncio.create_task(self.monitor_idle())
                order, _ = await self.queue_input_b.get()
                print(f'[Handler]: get new order from input b to storage: {order}')
                
                async with self.lock_processor:
                    task_idle_monitor.cancel()
                    await self._move_home_b()
                    await self._raise_product()
                    await self._move_product()
                    await self._release_product()
                    await self._move_home_b()
                    # aguarda para pegar o proximo item
                
                await asyncio.sleep(0.5)

    async def task_monitor_moving(self):
        while True:
            mov_x = await self.sensor_x.get_value()
            mov_z = await self.sensor_z.get_value()

            moving = mov_x or mov_z
            if moving and not self._is_moving:
                # Transição: PARADO -> MOVENDO
                print("[Handler]: Transição detectada: Parado -> Movendo")
                self._is_moving = True
                self._stopped_moving.clear()
                self._started_moving.set()

            elif not moving and self._is_moving:
                # Transição: MOVENDO -> PARADO
                print("[Handler]: Transição detectada: Movendo -> Parado")
                self._is_moving = False
                self._started_moving.clear()
                self._stopped_moving.set()

            await asyncio.sleep(0.05)

    async def monitor_idle(self):
        """
            Caso fique mais de 60 segundos ocioso, vai para posicção de idle
        """
        await asyncio.sleep(60)
        async with self.lock_processor:
            await self._move_position(self.idle_position)
    
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

        self.sensor_center = await self.base_node.add_variable(idx, f'IO:Sensor Meio {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_center.set_writable(True)

        self.sensor_left = await self.base_node.add_variable(idx, f'IO:Sensor Left {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_left.set_writable(True)

        self.sensor_right = await self.base_node.add_variable(idx, f'IO:Sensor Right {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.sensor_right.set_writable(True)

        # movimento
        self.handler_raise = await self.base_node.add_variable(idx, f'IO:Move Raise {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.handler_raise.set_writable(True)
        self.nodes.append(self.handler_raise)

        self.handler_move_leff = await self.base_node.add_variable(idx, f'IO:Move Left {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.handler_move_leff.set_writable(True)
        self.nodes.append(self.handler_move_leff)

        self.handler_move_right = await self.base_node.add_variable(idx, f'IO:Move Right {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.handler_move_right.set_writable(True)
        self.nodes.append(self.handler_move_right)

        self.position = await self.base_node.add_variable(idx, f'IO:Position {self.name}', 21474, varianttype=ua.VariantType.Int16)
        await self.position.set_writable(True)
        self.nodes.append(self.position)

    async def _move_home_a(self):
        await self._move_position(8)

    async def _move_home_b(self):
        await self._move_position(1)

    async def _raise_product(self):
        # move o handler esquerda, levanta o produto, volta ao centro e vai para o destino
        await self._move_handler_left()
        await self._move_raise()
        await self._move_handler_center()

    async def _move_product(self):
        await self._move_position(self._position)
        self._position += 1

    async def _release_product(self):
        # chegou na posição, baixa o elevador, retrai o handler e volta para a posicao
        await self._move_handler_right()
        await self._move_down()
        await self._move_handler_center()

    async def _move_position(self, position: int):
        self._started_moving.clear()
        self._stopped_moving.clear()

        await self.position.set_data_value(value=position, varianttype=VariantType.Int16)

        try:
            await asyncio.wait_for(self._started_moving.wait(), timeout=3.0)
            print("[Handler]: Movimento detectado! Aguardando parada...")
            
            await self._stopped_moving.wait()
            print(f"[Handler]: Movimento concluído. Elevador chegou na Posição {position}.")

        except asyncio.exceptions.TimeoutError:
            print(f"[Handler]: Movimento não detectado para P{position}. Assumindo que já estava no local.")
            self._stopped_moving.set()

        finally:
            await asyncio.sleep(2)
    
    async def _move_handler_left(self):
        # movimenta para a esquerda e espera chegar no sensor
        await self.handler_move_leff.set_value(True)
        await self.edge_handler_left.wait()
        await asyncio.sleep(2)

    async def _move_handler_center(self):
        # movimenta o handler para o centro
        await self.handler_move_leff.set_value(False)
        await self.handler_move_right.set_value(False)
        await self.edge_handler_center.wait()
        await asyncio.sleep(2)

    async def _move_handler_right(self):
        # movimenta para a direita e espera chegar no sensor
        await self.handler_move_right.set_value(True)
        await self.edge_handler_right.wait()
        await asyncio.sleep(2)

    async def _move_raise(self):
        await self.handler_raise.set_value(True)
        await self.edge_moving_z.wait()
        await asyncio.sleep(2)

    async def _move_down(self):
        await self.handler_raise.set_value(False)
        await self.edge_moving_z.wait()
        await asyncio.sleep(2)
