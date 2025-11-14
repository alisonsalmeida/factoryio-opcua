from typing import List, Dict, Optional, Callable, Set
from components.base import BaseComponent, BoxType
from asyncua import ua, Node
from components.base import EdgeDetector, EdgeType, EventSensorHandle
from components.order import Order, OrderFn, MoveCallbackFn, CoverType
from enum import Enum, auto

import asyncio


class Capabilities(Enum):
    PASS = 0
    DELIVERY_COVER = 1
    DELIVERY_NO_COVER = 2
    STORAGE_COVER = 3
    STORAGE_NO_COVER = 4


class RollerDirection(Enum):
    STOP = auto()
    FORWARD = auto()  # Para self.node_roll_plus
    BACKWARD = auto() # Para self.node_roll_minus


class TurnPosition(Enum):
    HOME = auto()     # Posição 0 (base)
    NINETY = auto()   # Posição 90 graus


class TurnTable(BaseComponent):
    def __init__(self, 
                 name, server, namespace_index, base_node,
                 capabilities: Set[Capabilities],
                 queue_input: asyncio.Queue[OrderFn],
                 queue_output: asyncio.Queue[OrderFn],
                 sem_output: asyncio.Semaphore
        ):
        
        super().__init__(name, server, namespace_index, base_node)

        self.capabilities: Set[Capabilities] = capabilities
        self.queue_input = queue_input
        self.queue_output = queue_output
        self.sem_output = sem_output
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
            order, move_prev_stage = await self.queue_input.get()

            await asyncio.sleep(1)
            box_type: BoxType = order.box_type
            capability = self._order_for_capability(order)

            if Capabilities.PASS in self.capabilities:
                if box_type == BoxType.BLUE:
                    # cria os triggers do sensor, para sinalizar que passou pelo turn table
                    front_detector = EdgeDetector(self.node_roll_front_limit.nodeid, ev_limit_front_sensor, EdgeType.FALLING)
                    back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.RISING)

                    handler.add_detect(front_detector)
                    handler.add_detect(back_detector)

                    await self.pass_box_blue(order, move_prev_stage, [front_detector, back_detector])
                    handler.clear() 

                elif box_type == BoxType.GREEN:
                    front_detector = EdgeDetector(self.node_roll_front_limit.nodeid, ev_limit_front_sensor, EdgeType.FALLING)
                    back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.RISING)
                    nineteen_detector = EdgeDetector(self.node_sensor_turn_nineteen.nodeid, ev_turn_90_sensor, EdgeType.RISING)
                    zero_detector = EdgeDetector(self.node_sensor_turn_zero.nodeid, ev_turn_0_sensor, EdgeType.RISING)

                    handler.add_detect(front_detector)
                    handler.add_detect(back_detector)
                    handler.add_detect(nineteen_detector)
                    handler.add_detect(zero_detector)

                    await self.pass_green_box(order, move_prev_stage, [front_detector, back_detector, nineteen_detector, zero_detector])
                    handler.clear()

                elif box_type == BoxType.METAL:
                    front_detector = EdgeDetector(self.node_roll_front_limit.nodeid, ev_limit_front_sensor, EdgeType.RISING)
                    back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.FALLING)
                    nineteen_detector = EdgeDetector(self.node_sensor_turn_nineteen.nodeid, ev_turn_90_sensor, EdgeType.RISING)
                    zero_detector = EdgeDetector(self.node_sensor_turn_zero.nodeid, ev_turn_0_sensor, EdgeType.RISING)

                    handler.add_detect(front_detector)
                    handler.add_detect(back_detector)
                    handler.add_detect(nineteen_detector)
                    handler.add_detect(zero_detector)

                    await self.pass_metal_box(order, move_prev_stage, [front_detector, back_detector, nineteen_detector, zero_detector])
                    handler.clear()
            
            else:
                if capability in self.capabilities:
                    if capability == Capabilities.DELIVERY_NO_COVER:
                        back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.RISING)
                        handler.add_detect(back_detector)

                        await self._no_cover_delivery(order, move_prev_stage, [back_detector])
                        handler.clear()

                    elif capability == Capabilities.STORAGE_NO_COVER:
                        back_detector = EdgeDetector(self.node_roll_back_limit.nodeid, ev_limit_back_sensor, EdgeType.RISING)
                        nineteen_detector = EdgeDetector(self.node_sensor_turn_nineteen.nodeid, ev_turn_90_sensor, EdgeType.RISING)
                        zero_detector = EdgeDetector(self.node_sensor_turn_zero.nodeid, ev_turn_0_sensor, EdgeType.RISING)
                        
                        handler.add_detect([back_detector, nineteen_detector, zero_detector])
                        await self._no_cover_storage(order, move_prev_stage, [back_detector, nineteen_detector, zero_detector])
                        handler.clear()

            await asyncio.sleep(1)

    async def pass_box_blue(self, order: Order, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
        # Ativa a esteira roll - e move o estagio anterior
        print(f'procesando caixa em turn table {self.name}: {order.box_type}')
        front_detector, back_detector = detectors

        await self.node_roll_minus.set_value(True)
        await move_prev_stage(True)

        # espera borda de descida do sensor de entrada, passou no primeiro, desliga a esteira anterior
        await front_detector.event_trigger.wait()
        front_detector.event_trigger.clear()         # renova o trigger
        await move_prev_stage(False)

        # desliga o roll minus e espera a conveyor pegar esse item, desliga a esteira para o front
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()          # renova o trigger
        await self.node_roll_minus.set_value(False)
        
        async with self.sem_output:
            await self.queue_output.put((order, self.move_to_next))
            await self.node_roll_minus.set_value(True)
        
        # configura borda de descida, e espera a caixa passar toda
        back_detector.set_trigger(EdgeType.FALLING)
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()

        await asyncio.sleep(0.3)
        await self.node_roll_minus.set_value(False)
        print(f'finalizou em {self.name}: {order.box_type}')

    async def pass_green_box(self, order: Order, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
        print(f'procesando caixa em turn table {self.name}: {order.box_type}')
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

        # volta a posição normal e espera a conveyor pega esse item
        await self.node_move_turn.set_value(False)
        await zero_detector.event_trigger.wait()
        zero_detector.event_trigger.clear()
        await asyncio.sleep(0.5)

        async with self.sem_output:
            await self.queue_output.put((order, self.move_to_next))

        # move a caixa para o proximo
        await self.node_roll_minus.set_value(True)
        back_detector.set_trigger(EdgeType.FALLING)     # agora é borda de descida
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()
        front_detector.event_trigger.clear()
        
        await asyncio.sleep(0.3)
        await self.node_roll_minus.set_value(False)
        print(f'finalizou em {self.name}: {order.box_type}')

    async def pass_metal_box(self, order: Order, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
        print(f'procesando caixa em turn table {self.name}: {order.box_type}')
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

        async with self.sem_output:
            await self.queue_output.put((order, self.move_to_next))

        # move a caixa para o proximo
        back_detector.enable = True
        await self.node_roll_minus.set_value(True)
        # back_detector.set_trigger(EdgeType.FALLING)     # agora é borda de descida
        
        await back_detector.event_trigger.wait()
        back_detector.event_trigger.clear()
        
        await asyncio.sleep(0.3)
        await self.node_roll_minus.set_value(False)
        print(f'finalizou em {self.name}: {order.box_type}')

    async def _set_rollers(self, direction: RollerDirection):
        """
        Controla os rolos (roldanas) da mesa.
        Esta função garante que um motor pare antes de o outro ligar.
        """
        if direction == RollerDirection.STOP:
            await self.node_roll_minus.set_value(False)
            await self.node_roll_plus.set_value(False)
        
        elif direction == RollerDirection.FORWARD:
            await self.node_roll_minus.set_value(False) # Garante que o oposto está parado
            await self.node_roll_plus.set_value(True)
        
        elif direction == RollerDirection.BACKWARD:
            await self.node_roll_plus.set_value(False) # Garante que o oposto está parado
            await self.node_roll_minus.set_value(True)
        
        await asyncio.sleep(0.1)

    async def _rotate_to(self, position: TurnPosition, detectors: Dict[str, EdgeDetector]):
        """Gira a mesa para uma posição e espera pelo sensor de confirmação."""
        if position == TurnPosition.HOME:
            await self.node_move_turn.set_value(False)
            await self._wait_for_sensor(detectors['zero'])

        elif position == TurnPosition.NINETY:
            await self.node_move_turn.set_value(True)
            await self._wait_for_sensor(detectors['ninety'])
    
    async def _wait_for_sensor(self, detector: EdgeDetector, new_edge: Optional[EdgeType] = None):
        """
        Espera por um evento de sensor e limpa o gatilho.
        Opcionalmente, reconfigura o gatilho para a próxima detecção.
        """
        await detector.event_trigger.wait()
        detector.event_trigger.clear()
        
        if new_edge:
            detector.set_trigger(new_edge)

    async def _control_previous_stage(self, move_prev_stage_fn: Callable, move: bool):
        """Controla a esteira do estágio anterior (liga/desliga)."""
        await move_prev_stage_fn(move)

    async def _transfer_to_next_stage(self, order: Order):
        """Coloca a ordem na fila de saída para o próximo componente."""
        print(f"  -> Enviando item {order.box_type} para a fila do próximo estágio.")
        await self.queue_output.put((order, self.move_to_next))
    
    def _order_for_capability(self, order: Order) -> Capabilities:
        if order.delivery is True:
            cover = True if order.cover == CoverType.WITH_COVER else False
            return Capabilities.DELIVERY_COVER if cover else Capabilities.DELIVERY_NO_COVER

        elif order.delivery is False:
            cover = True if order.cover == CoverType.WITH_COVER else False
            return Capabilities.STORAGE_COVER if cover else Capabilities.STORAGE_NO_COVER
        
    # async def pass_box_blue(self, order: Order, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
    #     print(f'\n[INÍCIO] Processando {order.box_type} (Blue Box) em {self.name}')
    #     front_detector, back_detector = detectors

    #     # 1. Puxa a caixa do estágio anterior
    #     await self._set_rollers(RollerDirection.BACKWARD)
    #     await self._control_previous_stage(True, move_prev_stage)

    #     # 2. Caixa passou do sensor da frente, para a esteira anterior
    #     await self._wait_for_sensor(front_detector)
    #     await self._control_previous_stage(False, move_prev_stage)
    #     await asyncio.sleep(0.5)

    #     # 3. Caixa chegou ao sensor de trás (pronta para sair)
    #     await self._wait_for_sensor(back_detector)
    #     await self._set_rollers(RollerDirection.STOP)
        
    #     # 4. Avisa o próximo estágio que a caixa está pronta
    #     await self._transfer_to_next_stage(order)
        
    #     # 5. Próximo estágio começou a puxar (via self.move_to_next),
    #     #    então ligamos nossas roldanas para ajudar a empurrar.
    #     await self._set_rollers(RollerDirection.BACKWARD)
        
    #     # 6. Espera a caixa sair totalmente (borda de descida)
    #     await self._wait_for_sensor(back_detector, new_edge=EdgeType.FALLING)
        
    #     await asyncio.sleep(0.3)
    #     await self._set_rollers(RollerDirection.STOP)
    #     print(f'[FIM] Finalizou {order.box_type} em {self.name}')

    # async def pass_green_box(self, order: Order, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
    #     print(f'\n[INÍCIO] Processando {order.box_type} (Green Box) em {self.name}')
    #     front_detector, back_detector, nineteen_detector, zero_detector = detectors
    #     turn_detectors = {'ninety': nineteen_detector, 'zero': zero_detector}

    #     # 1. Gira para a posição de 90 graus
    #     await self._rotate_to(TurnPosition.NINETY, turn_detectors)
    #     await asyncio.sleep(0.5)

    #     # 2. Puxa a caixa do estágio anterior
    #     await self._set_rollers(RollerDirection.BACKWARD)
    #     await self._control_previous_stage(True, move_prev_stage)

    #     # 3. Caixa chegou ao sensor de trás
    #     await self._wait_for_sensor(back_detector)
    #     await self._set_rollers(RollerDirection.STOP)
    #     await self._control_previous_stage(False, move_prev_stage)
    #     await asyncio.sleep(0.5)

    #     # 4. Gira de volta para a posição inicial (0 graus)
    #     await self._rotate_to(TurnPosition.HOME, turn_detectors)
    #     await asyncio.sleep(0.5)

    #     # 5. Avisa o próximo estágio
    #     await self._transfer_to_next_stage(order)

    #     # 6. Próximo estágio está puxando, ajuda a empurrar
    #     await self._set_rollers(RollerDirection.BACKWARD)
        
    #     # 7. Espera a caixa sair totalmente (borda de descida)
    #     await self._wait_for_sensor(back_detector, new_edge=EdgeType.FALLING)
    #     front_detector.event_trigger.clear() # Limpa o sensor da frente por segurança
        
    #     await asyncio.sleep(0.3)
    #     await self._set_rollers(RollerDirection.STOP)
    #     print(f'[FIM] Finalizou {order.box_type} em {self.name}')

    # async def pass_metal_box(self, order: Order, move_prev_stage: callable, detectors: List[EdgeDetector] = []):
        # print(f'\n[INÍCIO] Processando {order.box_type} (Metal Box) em {self.name}')
        # front_detector, back_detector, nineteen_detector, zero_detector = detectors
        # turn_detectors = {'ninety': nineteen_detector, 'zero': zero_detector}

        # # 1. Gira para a posição de 90 graus
        # await self._rotate_to(TurnPosition.NINETY, turn_detectors)
        # back_detector.enable = False # Desativa sensor de trás
        # await asyncio.sleep(0.5)

        # # 2. Puxa a caixa (para FRENTE)
        # await self._set_rollers(RollerDirection.FORWARD)
        # await self._control_previous_stage(True, move_prev_stage)

        # # 3. Caixa chegou ao sensor da FRENTE
        # await self._wait_for_sensor(front_detector)
        # await self._set_rollers(RollerDirection.STOP)
        # await self._control_previous_stage(False, move_prev_stage)
        # await asyncio.sleep(0.5)

        # # 4. Gira de volta para a posição inicial (0 graus)
        # await self._rotate_to(TurnPosition.HOME, turn_detectors)
        # await asyncio.sleep(0.5)

        # # 5. Avisa o próximo estágio
        # back_detector.enable = True # Reativa sensor de trás
        # await self._transfer_to_next_stage(order)

        # # 6. Próximo estágio está puxando (do nosso ponto de vista, é PARA TRÁS)
        # await self._set_rollers(RollerDirection.BACKWARD)
        
        # # 7. Espera a caixa sair totalmente
        # await self._wait_for_sensor(back_detector) # Borda de subida (default)
        
        # await asyncio.sleep(0.3)
        # await self._set_rollers(RollerDirection.STOP)
        # print(f'[FIM] Finalizou {order.box_type} em {self.name}')
    
    async def _no_cover_storage(self, order: Order, move_prev_stage: MoveCallbackFn, detectors: List[EdgeDetector] = []):
        """
            Movimenta para armazenar sem tampas
        """
        print(f'[Turn Table: {self.name}]: moving order: {order} to storage no with cover')
        back_detector, nineteen_detector, zero_detector = detectors

        # puxa a caixa para frente e liga o estagio anterior ate o sensor de backlimit ser acionado na borda de subida
        # 2. Puxa a caixa (para FRENTE)
        
        await self._set_rollers(RollerDirection.BACKWARD)
        await self._control_previous_stage(move_prev_stage, True)
        await self._wait_for_sensor(back_detector)
        await self._set_rollers(RollerDirection.STOP)
        await self._control_previous_stage(move_prev_stage, False)
        await asyncio.sleep(0.5)

        # gira 90 graus
        await self._rotate_to(TurnPosition.NINETY, {'ninety': nineteen_detector})
        await asyncio.sleep(0.5)

        # passa para o proximo estagio e espera o proximo estagio puxar
        await self._transfer_to_next_stage(order)
        
        # proximo estagio puxou, aguarda o sensor de backward dar borda de descida e
        # reconfigura para borda de subida novamente e volta a posição normal
        back_detector.set_trigger(EdgeType.FALLING)
        await self._set_rollers(RollerDirection.BACKWARD)
        await self._wait_for_sensor(back_detector, EdgeType.RISING)
        await self._set_rollers(RollerDirection.STOP)

        await asyncio.sleep(1)
        await self._rotate_to(TurnPosition.HOME, {'zero': zero_detector})

    async def _no_cover_delivery(self, order: Order, move_prev_stage: MoveCallbackFn, detectors: List[EdgeDetector] = []):
        print(f'[Turn Table: {self.name}]: moving order: {order} to delivery no with cover')
        back_detector = detectors[0]

        await self._set_rollers(RollerDirection.BACKWARD)
        await self._control_previous_stage(move_prev_stage, True)
        await self._wait_for_sensor(back_detector, EdgeType.FALLING)
        await self._set_rollers(RollerDirection.STOP)
        await self._control_previous_stage(move_prev_stage, False)
        await self._transfer_to_next_stage(order)

        await self._set_rollers(RollerDirection.BACKWARD)
        await self._wait_for_sensor(back_detector)
        await asyncio.sleep(0.5)
        await self._set_rollers(RollerDirection.STOP)
