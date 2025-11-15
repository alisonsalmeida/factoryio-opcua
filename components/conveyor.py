from typing import Set, List
from components.base import BaseComponent, EventSensorHandle, EdgeDetector, EdgeType
from components.order import Order, OrderFn, OrderState
from asyncua import ua, Node
from enum import Enum, auto

import asyncio


class ConveyorDirection(Enum):
    BACKWARD = auto()
    FORWARD = auto()


class Conveyor(BaseComponent):
    def __init__(
            self, name, server, namespace_index, base_node,
            num_engines: int,
            max_items: int,
            directions: Set[ConveyorDirection],
            queue_input: asyncio.Queue[OrderFn],
            queue_output: asyncio.Queue[OrderFn],
            sem_input: asyncio.Semaphore,
            wait_next_stage: bool = True
        ):
        
        super().__init__(name, server, namespace_index, base_node)
        
        self.num_engines = num_engines
        self.max_items = max_items
        self.directions = directions
        self.num_sensors = 2
        self.engines: List[Node] = []
        self.sensors: List[Node] = []
        self.queue_input = queue_input
        self.queue_output = queue_output
        self.sem_input = sem_input
        self.wait_next_stage = wait_next_stage

        self.items = 0
        self.lock_engines = asyncio.Lock()

    async def build(self):
        idx = self.namespace_index
        name = 'IO: Engine:'
        multiply = len(self.directions)

        for i in range(0, self.num_engines * multiply):
            node = await self.base_node.add_variable(idx, name + f'{i} {self.name}', False, varianttype=ua.VariantType.Boolean)
            await node.set_writable(True)

            self.engines.append(node)
            self.nodes.append(node)

        # gera os sensores
        names = [f'IO:Sensor Start {self.name}', f'IO:Sensor End {self.name}']
        for i in range(0, self.num_sensors):
            node = await self.base_node.add_variable(self.namespace_index, names[i], False, varianttype=ua.VariantType.Boolean)
            await node.set_writable(True)
            self.sensors.append(node)
    
    async def run(self):
        ev_start_sensor = asyncio.Event()
        ev_end_sensor = asyncio.Event()
        start_edge_detector = EdgeDetector(self.sensors[0].nodeid, ev_start_sensor, EdgeType.FALLING)
        end_edge_detector = EdgeDetector(self.sensors[1].nodeid, ev_end_sensor, EdgeType.RISING)

        handler = EventSensorHandle(self.server, [start_edge_detector, end_edge_detector])
        sub = await self.server.create_subscription(10, handler)        
        await sub.subscribe_data_change(self.sensors)

        await self.start_event.wait()

        while True:
            await self.sem_input.acquire()
            order, _ = await self.queue_input.get()
            self.items += 1

            # retirada, roda ao contrario os motores das esteiras que giram para ambos sentidos
            if order.state == OrderState.WITHDRAWAL:
                continue

            else:
                # aqui é simples (simples o caralho), liga os motores, espera o a borda de descida do sensor de entrada
                # para desligar a esteira           
                asyncio.create_task(self.task_move_front(order, start_edge_detector, end_edge_detector))

    async def task_move_front(self, order: Order, start_edge_detector: EdgeDetector, end_edge_detector: EdgeDetector):
        async with self.lock_engines:
            await self._move(ConveyorDirection.FORWARD, True)
            await start_edge_detector.event_trigger.wait()
            start_edge_detector.event_trigger.clear()

            await self._move(ConveyorDirection.FORWARD, False)

        if self.items < self.max_items:
            async with self.lock_engines:
                await self._move(ConveyorDirection.FORWARD, True)
                await end_edge_detector.event_trigger.wait()
                end_edge_detector.event_trigger.clear()

                # chegou no final, desliga todos os motores
                await self._move(ConveyorDirection.FORWARD, False)
            
            # # passa o item para o proximo processar
            await self.queue_output.put((order, self.move_to_next))
            self.items -= 1
            
            end_edge_detector.set_trigger(EdgeType.FALLING)
            await end_edge_detector.event_trigger.wait()
            end_edge_detector.event_trigger.clear()

            self.sem_input.release()
            end_edge_detector.set_trigger(EdgeType.RISING)

        # numero maximo de elementos
        else:
            await self.queue_output.put((order, self.move_to_next))
            self.items -= 1
            
            end_edge_detector.set_trigger(EdgeType.FALLING)
            await end_edge_detector.event_trigger.wait()
            end_edge_detector.event_trigger.clear()

            self.sem_input.release()
            end_edge_detector.set_trigger(EdgeType.RISING)

    async def _move(self, direction: ConveyorDirection, state: bool):
        # verifica se gira para ambos lados
        if len(self.directions) > 1:
            # gira os pares, sao pra frente
            if direction == ConveyorDirection.FORWARD:
                for i, engine in enumerate(self.engines):
                    if i % 2 == 0:
                        await engine.set_value(state)
            
            # os impares sao para tras
            elif direction == ConveyorDirection.BACKWARD:
                for i, engine in enumerate(self.engines):
                    if i % 2 != 0:
                        await engine.set_value(state)

            return
        
        for i, engine in enumerate(self.engines):
            await engine.set_value(state)

    async def move_to_next(self, value):
        async with self.lock_engines:
            await self.engines[self.num_engines - 1].set_value(value)


class ConveyorAccess(Conveyor):
    # if order.state == OrderState.WITHDRAWAL:

    async def run(self):
        print('[Conveyor Access]: start process task')
        ev_end_sensor = asyncio.Event()
        end_edge_detector = EdgeDetector(self.sensors[1].nodeid, ev_end_sensor, EdgeType.FALLING)

        handler = EventSensorHandle(self.server, [end_edge_detector])
        sub = await self.server.create_subscription(10, handler)        
        await sub.subscribe_data_change(self.sensors)

        await self.start_event.wait()

        while True:
            order, move_next_fn = await self.queue_input.get()
            print(f'[Conveyor Access]: {order}')
            await asyncio.sleep(1)

            # liga o motor 0, que é pra frente, espera chegar no sensor, é borda de descida
            await self.engines[0].set_value(True)
            await move_next_fn(True)

            await end_edge_detector.wait()
            
            await self.engines[0].set_value(False)
            await move_next_fn(False)

            # chegou na borda, avisa o handler que chegou
            async with self.sem_input:
                await self.queue_output.put((order, self.move_to_next))
            
            # espera o handler puxar
            # await end_edge_detector.set_trigger(EdgeType.RISING)
            if self.wait_next_stage:
                await end_edge_detector.wait()

            # await end_edge_detector.set_trigger(EdgeType.FALLING)
            await asyncio.sleep(1)
            print(f'[Conveyor Access]: get next order')
