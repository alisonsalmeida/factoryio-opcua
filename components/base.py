from abc import abstractmethod, ABC
from asyncua import Node, Server
from asyncua.ua import NodeId
from enum import Enum, auto

import asyncio


class BaseComponent:
    def __init__(self, name: str, server: Server, namespace_index: int, base_node: Node):
        self.name = name
        self.server = server
        self.namespace_index = namespace_index
        self.base_node = base_node
        self.start_event = asyncio.Event()
    
    @abstractmethod
    async def run(self):
        raise NotImplementedError
    
    @abstractmethod
    async def build(self):
        raise NotImplementedError
    
    async def move_to_next(self):
        pass

    async def move_to_prev(self):
        pass


class EdgeType(Enum):
    RISING = auto()
    FALLING = auto()
    BOTH = auto()


class State(Enum):
    LOW = 0
    HIGH = 1


class EdgeDetector:
    def __init__(self, node_id: NodeId, event: asyncio.Event, trigger_on=EdgeType.RISING, enable=True):
        """
        :param trigger_on: EdgeType.RISING, EdgeType.FALLING ou EdgeType.BOTH
        :param callback: função chamada quando o trigger ocorre
        """
        
        self.node_id = node_id
        self.state = State.LOW
        self.trigger_on = trigger_on
        self.event_trigger = event
        self.enable = enable
    
    def update(self, signal_value: int, name: str):
        """Atualiza o estado com o novo valor do sensor (0 ou 1)."""
        if self.enable is False:
            return
        
        new_state = State.HIGH if signal_value else State.LOW

        # Detecta bordas
        if self.state == State.LOW and new_state == State.HIGH:
            edge = EdgeType.RISING
        elif self.state == State.HIGH and new_state == State.LOW:
            edge = EdgeType.FALLING
        else:
            edge = None

        # Atualiza estado
        self.state = new_state

        # Verifica se deve acionar callback
        if edge:
            if self.trigger_on == EdgeType.BOTH or self.trigger_on == edge:
                print(f'Trigger Event: {self.trigger_on} for node_id: {name}')
                self.event_trigger.set()
    
    def set_trigger(self, trigger_on: EdgeType):
        """Permite mudar o tipo de borda que dispara o trigger."""
        self.trigger_on = trigger_on

    def set_enable(self, value):
        self.enable = value


class EventSensorHandle:
    def __init__(self, server: Server, edge_detectors: list[EdgeDetector]):
        self.server = server
        self.edge_detectors = edge_detectors

    async def datachange_notification(self, node: Node, val, data):
       name = await node.read_browse_name()
       value = int(val)

       for edge_detector in self.edge_detectors:
           if node.nodeid == edge_detector.node_id:
               edge_detector.update(value, name)

    async def event_notification(self, event):
        pass

    async def add_detect(self, edge_detector: EdgeDetector):
        self.edge_detectors.append(edge_detector)
