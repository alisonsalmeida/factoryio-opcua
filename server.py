from typing import List
from pathlib import Path
from asyncua import Server, ua, Node
from asyncua.ua import NodeId
from asyncua.server.user_managers import CertificateUserManager
from asyncua.crypto.cert_gen import setup_self_signed_certificate
from asyncua.crypto.validator import CertificateValidator, CertificateValidatorOptions
from cryptography.x509.oid import ExtendedKeyUsageOID
from components.base import BaseComponent
from components.box_producer import BoxProducer, BoxType
from components.turn_table import TurnTable
from components.conveyor import Conveyor

import asyncio
import socket


async def main():
    cert_base = Path(__file__).parent
    server_cert = Path(cert_base / "certificates/server_certicate.der")
    server_private_key = Path(cert_base / "certificates/server_private_key.pem")

    cert_user_manager = CertificateUserManager()
    await cert_user_manager.add_user('certificates/server_certificate.der', name='test_user')

    host_name = socket.gethostname()
    server_app_uri = f"alisonalmeida@{host_name}"

    server = Server()
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
    empty_producer = await objects_node.add_object(idx, 'Empty Producer')
    node_turns_table = await objects_node.add_object(idx, 'TurnsTable')
    node_input_conveyors = await objects_node.add_object(idx, 'Conveyors')

    tasks: List[asyncio.Task] = []
    queue_producer_turntable = asyncio.Queue()
    
    producers: List[BaseComponent] = [
        BoxProducer(BoxType.GREEN, server, idx, green_producer, 2, 4, queue_producer_turntable),
        BoxProducer(BoxType.BLUE, server, idx, blue_producer, 2, 2, queue_producer_turntable),
        BoxProducer(BoxType.EMPTY, server, idx, empty_producer, 1, 4, queue_producer_turntable)
    ]

    for producer in producers:
        await producer.build()
        task = asyncio.create_task(producer.run(), name=producer.name)
        tasks.append(task)

    turns_table: List[BaseComponent] = [
        TurnTable('Select', server, idx, node_turns_table, {}, queue_producer_turntable),
        TurnTable('NoCover', server, idx, node_turns_table, {}, queue_producer_turntable),
        TurnTable('WithCover', server, idx, node_turns_table, {}, queue_producer_turntable)
    ]

    for turn_table in turns_table:
        base_node = await node_turns_table.add_object(idx, f'TurnTable {turn_table.name}')
        turn_table.base_node = base_node

        await turn_table.build()
        task = asyncio.create_task(turn_table.run(), name=turn_table.name)
        tasks.append(task)

    conveyors: List[BaseComponent] = [
        Conveyor('InputConveyor', server, idx, node_input_conveyors, 2),
        Conveyor('RollerAConveyor', server, idx, node_input_conveyors, 1),
        Conveyor('AccAConveyor', server, idx, node_input_conveyors, 1),
        Conveyor('DispaConveyor', server, idx, node_input_conveyors, 1),
        Conveyor('RollerBConveyor', server, idx, node_input_conveyors, 1),
        Conveyor('AccB1Conveyor', server, idx, node_input_conveyors, 1),
        Conveyor('ExitConveyor', server, idx, node_input_conveyors, 1)
    ]
    
    for conveyor in conveyors:
        base_node = await node_input_conveyors.add_object(idx, f'Conveyor {conveyor.name}')
        conveyor.base_node = base_node

        await conveyor.build()
        task = asyncio.create_task(conveyor.run(), name=conveyor.name)
        tasks.append(task)

    btn_start_process = await objects_node.add_variable(idx, 'IO:Botao Start Process', False, varianttype=ua.VariantType.Boolean)
    await btn_start_process.set_writable()

    btn_stop_process = await objects_node.add_variable(idx, 'IO:Botao Stop Process', False, varianttype=ua.VariantType.Boolean)
    await btn_stop_process.set_writable()

    await server.start()
    
    # melhorar esse pedaço
    process_run = False
    producer_green_task = None

    while True:
        value_start_button: bool = await btn_start_process.read_value()
        value_stop_button: bool = await btn_stop_process.read_value()

        if value_start_button and process_run is False:
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

            continue

        if value_stop_button and process_run is True:
            # pausa o processo
            process_run = False
            producer_green_task.cancel()
            continue
        
        await asyncio.sleep(0.01)


if __name__ == "__main__":
    asyncio.run(main())
