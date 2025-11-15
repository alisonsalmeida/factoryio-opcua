from components.base import BaseComponent, EdgeDetector, EdgeType, EventSensorHandle, BoxType
from components.order import Order, OrderFn, OrderState
from asyncua import Node, Server, ua
from typing import List, Optional, Tuple
from enum import Enum, auto

import asyncio


class BoxFeeder(BaseComponent):
    def __init__(self, order_producer_queue: asyncio.Queue[Order], box_type: BoxType, server: Server, namespace_index: int, base_node: Node, num_emitters: int, num_conveyors: int, queue: asyncio.Queue[OrderFn]):
        super().__init__(box_type.name, server, namespace_index, base_node)

        # enfileira caixas para o segundo estagio, passando o tipo e um metodo para avançar a ultima esteira
        self.order_producer_queue = order_producer_queue
        self.box_type = box_type
        self.queue = queue  
        self.num_emitters = num_emitters
        self.num_conveyors = num_conveyors

        self.emitters = []
        self.conveyors = []
        self.sensors = []

    async def enche_container(self, node_producer: Node):
        # await asyncio.sleep(1)
        await node_producer.set_value(True)
        await asyncio.sleep(5)
        await node_producer.set_value(False)

    async def run(self):
        producer_container = producer_product = None
        if self.num_emitters > 1:
            producer_container, producer_product = self.emitters

        else:
            producer_container = self.emitters[0]

        start_converyor: List[Node] = self.conveyors[0:2]
        end_conveyors: List[Optional[Node]] = None
        if self.num_conveyors > 2:
            end_conveyors = self.conveyors[2:]

        start_sensor, end_sensor = self.sensors

        ev_start_sensor = asyncio.Event()
        ev_end_sensor = asyncio.Event()

        # monitora as mudanças nos sensores
        edge_detectors = [
            EdgeDetector(start_sensor.nodeid, ev_start_sensor, EdgeType.FALLING),
            EdgeDetector(end_sensor.nodeid, ev_end_sensor, EdgeType.RISING)
        ]

        handler = EventSensorHandle(self.server, edge_detectors)

        sub = await self.server.create_subscription(10, handler)
        await sub.subscribe_data_change([start_sensor, end_sensor])
        await self.start_event.wait()

        print(f'[Feeder]: Starting box producer: {self.box_type.name}')
        is_full = False
        
        while True:
            # ja começa ligando a upper e down, desliga o evento do sensor de start
            order = await self.order_producer_queue.get()
            order.state = OrderState.PRODUCTION

            print(f'[Feeder]: Received production order: {order}')

            for _ in range(order.quantity):

                edge_detectors[0].set_enable(False)
                await producer_container.set_value(True)
                await asyncio.sleep(1)

                if is_full is False:
                    if producer_product:
                        await producer_product.set_value(True)
                    
                    # espera 5 segundo para encher, apos, liga a esteira 1 e 2, e desliga os 2 producer
                    await asyncio.sleep(5)

                edge_detectors[0].set_enable(True)      # habilita o evento do sensor 1, borda de descida

                if producer_product:
                    await producer_product.set_value(False)

                await asyncio.sleep(1)

                for conveyor in start_converyor:
                    await conveyor.set_value(True)
                        
                # espera sensor de start, dar a transição
                # quer dizer que a caixa moveu para a esteira 2
                await ev_start_sensor.wait()
                ev_start_sensor.clear()

                # desliga a esteira 1 e ja enche o proximo
                await start_converyor[0].set_value(False)

                if producer_product:
                    is_full = True
                    asyncio.create_task(self.enche_container(producer_product))
                
                # liga as esteiras 3 e 4
                if end_conveyors:
                    for conveyor in end_conveyors:
                        await conveyor.set_value(True)

                # espera chegar no final, desliga todas
                await ev_end_sensor.wait()
                ev_end_sensor.clear()

                if not end_conveyors:                
                    await start_converyor[1].set_value(False)

                else:
                    for conveyor in self.conveyors:
                        if conveyor is not None:
                            await conveyor.set_value(False)

                # configura o evento do sensor de stop, para ser de borda de descida
                # e depois continua o ciclo novamente
                # manda uma caixa para a fila do turntable
                await self.queue.put((order, self.move_to_next))

                # # espera o turn table puxar
                edge_detectors[1].set_trigger(EdgeType.FALLING)
                await ev_end_sensor.wait()

                ev_end_sensor.clear()
                edge_detectors[1].set_trigger(EdgeType.RISING)

    async def build(self):
        # gera os emitters
        names = [f'IO:Container {self.name}', f'IO:Product {self.name}']
        for i in range(0, self.num_emitters):
            node = await self.base_node.add_variable(self.namespace_index, names[i], False, varianttype=ua.VariantType.Boolean)
            await node.set_writable(True)
            self.emitters.append(node)
            self.nodes.append(node)

        # gera as esteiras
        names = f'IO:Conveyor {self.name}:'
        for i in range(0, self.num_conveyors):
            node = await self.base_node.add_variable(self.namespace_index, names + f'{i + 1}', False, varianttype=ua.VariantType.Boolean)
            await node.set_writable(True)
            self.conveyors.append(node)
            self.nodes.append(node)

        # gera os sensores
        names = [f'IO:Sensor Start {self.name}', f'IO:Sensor End {self.name}']
        for i in range(0, 2):
            node = await self.base_node.add_variable(self.namespace_index, names[i], False, varianttype=ua.VariantType.Boolean)
            await node.set_writable(True)
            self.sensors.append(node)

    async def move_to_next(self, value: bool):
        # liga ou desliga a ultima esteira desse estagio, permite que o turntable mova para frente
        await self.conveyors[self.num_conveyors - 1].set_value(value)
