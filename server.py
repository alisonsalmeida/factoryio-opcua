from typing import List, Tuple
from pathlib import Path
from asyncua import Server, ua, uamethod
from asyncua.server.user_managers import CertificateUserManager
from asyncua.crypto.cert_gen import setup_self_signed_certificate
from asyncua.crypto.validator import CertificateValidator, CertificateValidatorOptions
from cryptography.x509.oid import ExtendedKeyUsageOID
from components.base import BaseComponent
from components.box_producer import BoxFeeder, BoxType
from components.turn_table import TurnTable, Capabilities
from components.conveyor import Conveyor, ConveyorDirection, ConveyorAccess
from components.handler import Handler
from components.order import Order, OrderFn
from manager.order import ProcessOrder

import asyncio
import socket


class QueueRouter:
    """
        Essa classe serve para routear as ordens dos turn tables que tem mais de 1 saida
    """

    def __init__(self,
        queue_storage: asyncio.Queue[Order],
        queue_delivery: asyncio.Queue[OrderFn],
        sem_storage: asyncio.Semaphore,
        sem_delivery: asyncio.Semaphore
    ):
        
        self.queue_storage = queue_storage
        self.queue_delivery = queue_delivery
        self.sem_storage = sem_storage
        self.sem_delivery = sem_delivery

    async def put(self, item: OrderFn):
        order, fn = item

        if order.delivery:
            async with self.sem_delivery:
                await self.queue_delivery.put((order, fn))
        
        else:
            async with self.sem_storage:
                await self.queue_storage.put((order, fn))


async def task_simulate_consumer(queue):
    print('---> START QUEUE SIMULATE')

    while True:
        order, move_prev_fn = await queue.get()
        await move_prev_fn(True)
        await asyncio.sleep(3)
        await move_prev_fn(False)

        await asyncio.sleep(5)


async def main():
    cert_base = Path(__file__).parent
    server_cert = Path(cert_base / "certificates/server_certicate.der")
    server_private_key = Path(cert_base / "certificates/server_private_key.pem")

    cert_user_manager = CertificateUserManager()
    await cert_user_manager.add_user('certificates/server_certificate.der', name='test_user')

    host_name = socket.gethostname()
    server_app_uri = f"alisonalmeida@{host_name}"

    # queues for productions
    queue_oder_green: asyncio.Queue[Order] = asyncio.Queue()
    queue_oder_blue: asyncio.Queue[Order] = asyncio.Queue()
    queue_oder_metal: asyncio.Queue[Order] = asyncio.Queue()

    queue_producer_turntable: asyncio.Queue[OrderFn] = asyncio.Queue()                # feeder -> turntable
    queue_turntable1_conveyor1: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)     # turntable_select -> conveyor_input
    sem_turntable1_conveyor1 = asyncio.Semaphore(value=2)

    queue_conveyor1_turntable2: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)     # conveyor_input -> turntable_nocover
    queue_turntable2_storage: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)       # turntable2 -> roller_a_storage
    queue_turntable2_delivery: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)      # turntable2 -> conveyor_delivery
    sem_conveyor_storage = asyncio.Semaphore(value=2)
    sem_conveyor_delivery = asyncio.Semaphore(value=2)
    queue_turntable2_router = QueueRouter(queue_turntable2_storage, queue_turntable2_delivery, sem_conveyor_storage, sem_conveyor_delivery)

    queue_roller_a_acc_a: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)           # roller_a_storage -> roller_access_a
    queue_roller_b_acc_b: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)           # roller_b_storage -> roller_access_b
    queue_acc_a_handler: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)            # roller_access_a -> handler
    sem_acc_a_handler = asyncio.Semaphore(2)  
    queue_acc_b_handler: asyncio.Queue[OrderFn] = asyncio.Queue(maxsize=1)            # roller_access_b -> handler

    queue_simulate2 = asyncio.Queue()

    server = Server()
    process_order = ProcessOrder(queue_oder_green, queue_oder_blue, queue_oder_metal)
    await server.init()

    await server.set_application_uri(server_app_uri)
    server.set_endpoint('opc.tcp://0.0.0.0:4840')
    server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
    
    idx = await server.get_namespace_index(server_app_uri)

    await setup_self_signed_certificate(
        server_private_key,
        server_cert,
        server_app_uri,
        host_name,
        [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH],
        {
            "countryName": "BR",
            "stateOrProvinceName": "Amazonas",
            "localityName": "Manaus",
            "organizationName": "Bar Ltd",
        },
    )

    await server.load_certificate(str(server_cert))
    await server.load_private_key(str(server_private_key))

    validator = CertificateValidator(
            options=CertificateValidatorOptions.EXT_VALIDATION | CertificateValidatorOptions.PEER_CLIENT
        )
    
    server.set_certificate_validator(validator)

    objects_node = server.get_objects_node()
    green_producer = await objects_node.add_object(idx, 'Green Producer')
    blue_producer = await objects_node.add_object(idx, 'Blue Producer')
    metal_producer = await objects_node.add_object(idx, 'Metal Producer')
    node_turns_table = await objects_node.add_object(idx, 'TurnsTable')
    node_input_conveyors = await objects_node.add_object(idx, 'Conveyors')
    node_handler = await objects_node.add_object(idx, 'Handler')
    node_methods = await objects_node.add_object(idx, 'Methods')

    tasks: List[asyncio.Task] = []
    
    producers: List[BaseComponent] = [
        BoxFeeder(queue_oder_green, BoxType.GREEN, server, idx, green_producer, 2, 4, queue_producer_turntable),
        BoxFeeder(queue_oder_blue, BoxType.BLUE, server, idx, blue_producer, 2, 2, queue_producer_turntable),
        BoxFeeder(queue_oder_metal, BoxType.METAL, server, idx, metal_producer, 2, 4, queue_producer_turntable)
    ]

    for i, producer in enumerate(producers):
        await producer.build()
        task = asyncio.create_task(producer.run(), name=producer.name)
        tasks.append(task)

    turns_table: List[BaseComponent] = [
        TurnTable('Select', server, idx, node_turns_table, {Capabilities.PASS}, queue_producer_turntable, queue_turntable1_conveyor1, sem_turntable1_conveyor1),
        TurnTable('NoCover', server, idx, node_turns_table, {Capabilities.DELIVERY_NO_COVER, Capabilities.STORAGE_NO_COVER}, queue_conveyor1_turntable2, queue_turntable2_router, asyncio.Semaphore()),
        TurnTable('WithCover', server, idx, node_turns_table, {}, asyncio.Queue(), asyncio.Queue(), asyncio.Semaphore())
    ]

    for _, turn_table in enumerate(turns_table):
        base_node = await node_turns_table.add_object(idx, f'TurnTable {turn_table.name}')
        turn_table.base_node = base_node

        await turn_table.build()

        task = asyncio.create_task(turn_table.run(), name=turn_table.name)
        tasks.append(task)

    args_conveyors = [server, idx, node_input_conveyors]
    conveyors: List[BaseComponent] = [
        Conveyor('InputConveyor', *args_conveyors, 2, 2, {ConveyorDirection.FORWARD}, queue_turntable1_conveyor1, queue_conveyor1_turntable2, sem_turntable1_conveyor1),
        Conveyor('RollerAConveyor', *args_conveyors, 1, 4, {ConveyorDirection.FORWARD, ConveyorDirection.BACKWARD}, queue_turntable2_storage, queue_roller_a_acc_a, sem_conveyor_storage),
        ConveyorAccess('AccAConveyor', *args_conveyors, 1, 1, {ConveyorDirection.FORWARD, ConveyorDirection.BACKWARD}, queue_roller_a_acc_a, queue_acc_a_handler, sem_acc_a_handler),
        Conveyor('DispaConveyor', *args_conveyors, 1, 4, {ConveyorDirection.FORWARD}, queue_turntable2_delivery, queue_simulate2, sem_conveyor_delivery),
        Conveyor('RollerBConveyor', *args_conveyors, 1, 4, {ConveyorDirection.FORWARD, ConveyorDirection.BACKWARD}, asyncio.Queue(), asyncio.Queue(), asyncio.Semaphore()),
        ConveyorAccess('AccBConveyor', *args_conveyors, 1, 1, {ConveyorDirection.FORWARD, ConveyorDirection.BACKWARD},  asyncio.Queue(), asyncio.Queue(), asyncio.Semaphore()),
        Conveyor('ExitConveyor', *args_conveyors, 1, 1, {ConveyorDirection.FORWARD}, asyncio.Queue(), asyncio.Queue(), asyncio.Semaphore())
    ]
    
    for conveyor in conveyors:
        base_node = await node_input_conveyors.add_object(idx, f'Conveyor {conveyor.name}')
        conveyor.base_node = base_node

        await conveyor.build()
        task = asyncio.create_task(conveyor.run(), name=conveyor.name)
        tasks.append(task)

    handler = Handler('Handler', server, idx, node_handler, queue_acc_a_handler, queue_acc_b_handler, sem_acc_a_handler, asyncio.Semaphore())
    await handler.build()

    task = asyncio.create_task(handler.run(), name=handler.name)
    tasks.append(task)

    btn_start_process = await objects_node.add_variable(idx, 'IO:Botao Start Process', False, varianttype=ua.VariantType.Boolean)
    await btn_start_process.set_writable()

    btn_stop_process = await objects_node.add_variable(idx, 'IO:Botao Stop Process', False, varianttype=ua.VariantType.Boolean)
    await btn_stop_process.set_writable()

    input_args = [
        ua.Argument('ProductType', ua.NodeId(ua.VariantType.Int16)),
        ua.Argument('Quantity', ua.NodeId(ua.VariantType.Int16)),
        ua.Argument('Cover', ua.NodeId(ua.VariantType.Boolean)),
        ua.Argument('Delivery', ua.NodeId(ua.VariantType.Boolean)),
    ]
    
    output_args = [
        ua.Argument('Status', ua.NodeId(ua.VariantType.Boolean)),
        ua.Argument('Message', ua.NodeId(ua.VariantType.String))
    ]

    await node_methods.add_method(idx, 'CreateOrder', uamethod(process_order.handle_new_order), input_args, output_args)

    await server.start()
    # asyncio.create_task(task_simulate_consumer(queue_simulate))
    asyncio.create_task(task_simulate_consumer(queue_simulate2))

    print('server start')
    
    # melhorar esse pedaço
    process_run = False
    producer_green_task = None

    while True:
        value_start_button: bool = await btn_start_process.read_value()
        value_stop_button: bool = await btn_stop_process.read_value()

        if value_start_button and process_run is False:
            print('iniciando processo')

            process_run = True
            for producer in producers:
                producer.start_event.set()
                producer.start_event.clear()

            for turn_table in turns_table:
                turn_table.start_event.set()
                turn_table.start_event.clear()

            for conveyor in conveyors:
                conveyor.start_event.set()
                conveyor.start_event.clear()

            handler.start_event.set()
            handler.start_event.clear()

            continue

        if value_stop_button and process_run is True:
            print('parando processo')
            
            process_run = False
            for task in tasks:
                task.cancel()

            tasks.clear()

            for producer in producers:
                for node in producer.nodes:
                    await node.set_value(False)

                task = asyncio.create_task(producer.run(), name=producer.name)
                tasks.append(task)

            for turn_table in turns_table:
                for node in turn_table.nodes:
                    await node.set_value(False)
                    
                task = asyncio.create_task(turn_table.run(), name=turn_table.name)
                tasks.append(task)

            for conveyor in conveyors:
                for node in conveyor.nodes:
                    await node.set_value(False)

                task = asyncio.create_task(conveyor.run(), name=conveyor.name)
                tasks.append(task)

            task = asyncio.create_task(handler.run(), name=handler.name)
            tasks.append(task)

            continue
        
        await asyncio.sleep(0.01)


if __name__ == "__main__":
    asyncio.run(main())
