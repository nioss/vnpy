from time import sleep

from vnpy.event import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp
from vnpy.trader.event import EVENT_LOG
# from vnpy.gateway.ctp import CtpGateway
from vnpy.gateway.okexf import OkexfGateway
from vnpy.app.rpc_service import RpcServiceApp
from vnpy.app.rpc_service.engine import EVENT_RPC_LOG
from logging.handlers import TimedRotatingFileHandler
import logging


def init_log(name):
    logFilePath = "%s.log" % name
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = TimedRotatingFileHandler(logFilePath, when="d", interval=1, backupCount=30, encoding="UTF-8")
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger

def main_ui():
    """"""
    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)

    # main_engine.add_gateway(CtpGateway)
    main_engine.add_gateway(OkexfGateway)
    main_engine.add_app(RpcServiceApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


def process_log_event(event: Event):
    """"""
    log = event.data
    msg = f"{log.time}\t{log.msg}"

    logger.info(msg)


def main_terminal():
    """"""
    event_engine = EventEngine()
    event_engine.register(EVENT_LOG, process_log_event)
    event_engine.register(EVENT_RPC_LOG, process_log_event)

    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(OkexfGateway)
    rpc_engine = main_engine.add_app(RpcServiceApp)

    OKEX_API = {
        "API Key": "ad9c804d-e263-4b2a-9e90-3b960828a4b3",
        "Secret Key": "CBF74F9CC4DA6B7AE07F6F1FA5248AAB",
        "Passphrase": "ouyang",
        "Leverage": 20,
        "\u4f1a\u8bdd\u6570": 3,
        "\u4ee3\u7406\u5730\u5740": "",
        "\u4ee3\u7406\u7aef\u53e3": ""
    }
    main_engine.connect(OKEX_API, "OKEXF")
    sleep(10)

    rep_address = "tcp://127.0.0.1:2014"
    pub_address = "tcp://127.0.0.1:4102"
    rpc_engine.start(rep_address, pub_address)

    while True:
        sleep(1)


if __name__ == "__main__":
    # Run in GUI mode
    # main_ui()

    # Run in CLI mode
    logger = init_log('rpcServer')
    main_terminal()
