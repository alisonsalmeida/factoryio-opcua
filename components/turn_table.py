from typing import Tuple, List
from components.base import BaseComponent
from components.box_producer import BoxType
from asyncua import ua, Node
from components.base import EdgeDetector, EdgeType, EventSensorHandle
from components.order import Order

import asyncio


class TurnTable(BaseComponent):
    def __init__(self, name, server, namespace_index, base_node, steps: dict, queue: asyncio.Queue[Tuple[Order, callable]]):
        super().__init__(name, server, namespace_index, base_node)

        self.steps: dict = steps
        self.queue = queue
        self.sensors: List[Node] = []

    async def build(self):
        # cria os movimentos
        self.node_move_turn = await self.base_node.add_variable(self.namespace_index, f'IO: Rotate {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_move_turn.set_writable(True)
        self.nodes.append(self.node_move_turn)

        self.node_roll_plus = await self.base_node.add_variable(self.namespace_index, f'IO: Roll+ {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_plus.set_writable(True)
        self.nodes.append(self.node_roll_plus)

        self.node_roll_minus = await self.base_node.add_variable(self.namespace_index, f'IO: Roll- {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_minus.set_writable(True)
        self.nodes.append(self.node_roll_minus)

        # cria os sensores
        self.node_sensor_turn_zero = await self.base_node.add_variable(self.namespace_index, f'IO: Turn0 {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_sensor_turn_zero.set_writable(True)
        self.sensors.append(self.node_sensor_turn_zero)

        self.node_sensor_turn_nineteen = await self.base_node.add_variable(self.namespace_index, f'IO: Turn90 {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_sensor_turn_nineteen.set_writable(True)
        self.sensors.append(self.node_sensor_turn_nineteen)

        self.node_roll_front_limit = await self.base_node.add_variable(self.namespace_index, f'IO: LimitFront {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_front_limit.set_writable(True)
        self.sensors.append(self.node_roll_front_limit)

        self.node_roll_back_limit = await self.base_node.add_variable(self.namespace_index, f'IO: LimitBack {self.name}', False, varianttype=ua.VariantType.Boolean)
        await self.node_roll_back_limit.set_writable(True)
        self.sensors.append(self.node_roll_back_limit)

    async def run(self):
        ev_turn_0_sensor = asyncio.Event()
        ev_turn_90_sensor = asyncio.Event()
        ev_limit_front_sensor = asyncio.Event()
        ev_limit_back_sensor = asyncio.Event()

        handler = EventSensorHandle(self.server, [])
        sub = await self.server.create_subscription(10, handler)        
        await sub.subscribe_data_change(self.sensors)
        await self.start_event.wait()
        
        while True:
            order, move_prev_stage = await self.queue.get()
            await asyncio.sleep(1)
            box_type: BoxType = order.box_type

            if box_type == BoxType.BLUE:
                # cria os triggers do sensor, para sinalizar que passou pelo turn table
                front_detector = EdgeDetector(self.node_roll_front_limit.nodeid, ev_limit_front_sensor, EdgeType.FALLING)
                back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.FALLING)

                await handler.add_detect(front_detector)
                await handler.add_detect(back_detector)

                await self.pass_box_blue(box_type, move_prev_stage, [front_detector, back_detector])
                handler.edge_detectors.clear()

            elif box_type == BoxType.GREEN:
                front_detector = EdgeDetector(self.node_roll_front_limit.nodeid, ev_limit_front_sensor, EdgeType.FALLING)
                back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.RISING)
                nineteen_detector = EdgeDetector(self.node_sensor_turn_nineteen.nodeid, ev_turn_90_sensor, EdgeType.RISING)
                zero_detector = EdgeDetector(self.node_sensor_turn_zero.nodeid, ev_turn_0_sensor, EdgeType.RISING)

                await handler.add_detect(front_detector)
                await handler.add_detect(back_detector)
                await handler.add_detect(nineteen_detector)
                await handler.add_detect(zero_detector)

                await self.pass_gree_box(box_type, move_prev_stage, [front_detector, back_detector, nineteen_detector, zero_detector])
                handler.edge_detectors.clear()

            elif box_type == BoxType.METAL:
                front_detector = EdgeDetector(self.node_roll_front_limit.nodeid, ev_limit_front_sensor, EdgeType.RISING)
                back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.FALLING)
                nineteen_detector = EdgeDetector(self.node_sensor_turn_nineteen.nodeid, ev_turn_90_sensor, EdgeType.RISING)
                zero_detector = EdgeDetector(self.node_sensor_turn_zero.nodeid, ev_turn_0_sensor, EdgeType.RISING)

                await handler.add_detect(front_detector)
                await handler.add_detect(back_detector)
                await handler.add_detect(nineteen_detector)
                await handler.add_detect(zero_detector)

                await self.pass_metal_box(box_type, move_prev_stage, [front_detector, back_detector, nineteen_detector, zero_detector])
                handler.edge_detectors.clear()

            await asyncio.sleep(1)

    # se for azul
    async def pass_box_blue(self, box_type: BoxType, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
        # Ativa a esteira roll - e move o estagio anterior
        print(f'procesando caixa em turn table {self.name}: {box_type}')
        front_detector, back_detector = detectors

        await self.node_roll_minus.set_value(True)
        await move_prev_stage(True)

        # espera borda de descida do sensor de entrada, passou no primeiro, desliga a esteira anterior
        await front_detector.event_trigger.wait()
        front_detector.event_trigger.clear()         # renova o trigger
        await move_prev_stage(False)
        await asyncio.sleep(0.5)

        # espera passar toda, la ele
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()          # renova o trigger

        # desliga a esteira para o front
        await asyncio.sleep(0.3)                       # serve para simular o trigger da proxima esteira, FAAAZ o L
        await self.node_roll_minus.set_value(False)

        print(f'finalizou em {self.name}: {box_type}')

    async def pass_gree_box(self, box_type: BoxType, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
        print(f'procesando caixa em turn table {self.name}: {box_type}')
        front_detector, back_detector, nineteen_detector, zero_detector = detectors

        # rodar para 90 graus, esperar sensor, mover para roll-  esperar chegar no sensor limit-,
        # rodar para 0, esperar chegar em 0, mover para frente e esperar passar toda
        await self.node_move_turn.set_value(True)
        await nineteen_detector.event_trigger.wait()
        nineteen_detector.event_trigger.clear()

        # move a esteira anterior e o rool
        await asyncio.sleep(0.5)
        await self.node_roll_minus.set_value(True)
        await move_prev_stage(True)
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()

        await self.node_roll_minus.set_value(False)
        await move_prev_stage(False)
        await asyncio.sleep(0.5)

        # volta a posição normal
        await self.node_move_turn.set_value(False)
        await zero_detector.event_trigger.wait()
        zero_detector.event_trigger.clear()
        await asyncio.sleep(0.5)

        # move a caixa para o proximo
        await self.node_roll_minus.set_value(True)
        back_detector.set_trigger(EdgeType.FALLING)     # agora é borda de descida
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()
        front_detector.event_trigger.clear()
        
        # simula passar pelo segundo sensor
        await asyncio.sleep(0.3)
        await self.node_roll_minus.set_value(False)
        print(f'finalizou em {self.name}: {box_type}')

    async def pass_metal_box(self, box_type: BoxType, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
        print(f'procesando caixa em turn table {self.name}: {box_type}')
        front_detector, back_detector, nineteen_detector, zero_detector = detectors

        # rodar para 90 graus, esperar sensor, mover para roll+  esperar chegar no sensor limit+,
        # rodar para 0, esperar chegar em 0, mover para frente e esperar passar toda
        await self.node_move_turn.set_value(True)
        await nineteen_detector.event_trigger.wait()
        nineteen_detector.event_trigger.clear()
        back_detector.enable = False

        # move a esteira anterior e o rool
        await asyncio.sleep(0.5)
        await self.node_roll_plus.set_value(True)
        await move_prev_stage(True)
        await front_detector.event_trigger.wait()
        front_detector.event_trigger.clear()

        await self.node_roll_plus.set_value(False)
        await move_prev_stage(False)
        await asyncio.sleep(0.5)

        # volta a posição normal
        await self.node_move_turn.set_value(False)
        await zero_detector.event_trigger.wait()
        zero_detector.event_trigger.clear()
        await asyncio.sleep(0.5)

        # move a caixa para o proximo
        back_detector.enable = True
        await self.node_roll_minus.set_value(True)
        # back_detector.set_trigger(EdgeType.FALLING)     # agora é borda de descida
        
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()
        
        # simula passar pelo segundo sensor
        await asyncio.sleep(0.3)
        await self.node_roll_minus.set_value(False)
        print(f'finalizou em {self.name}: {box_type}')