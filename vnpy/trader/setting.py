"""
Global setting of VN Trader.
"""

# from logging import CRITICAL
from logging import DEBUG

from .utility import load_json

SETTINGS = {
    "font.family": "Arial",
    "font.size": 12,

    "log.active": True,
    "log.level": DEBUG,
    "log.console": True,
    "log.file": True,

    "email.server": "smtp.qq.com",
    "email.port": 465,
    "email.username": "",
    "email.password": "",
    "email.sender": "",
    "email.receiver": "",

    "rqdata.username": "",
    "rqdata.password": "",

    # "database.driver": "sqlite",  # see database.Driver
    "database.driver": "mongodb",  # see database.Driver
    # "database.database": "database.db",  # for sqlite, use this as filepath
    "database.database": "vnpy",  # for sqlite, use this as filepath
    "database.host": "localhost",
    "database.port": 27017,
    # "database.port": 3306,
    "database.user": "",
    "database.password": "",
    "database.authentication_source": "admin",  # for mongodb
}

# Load global setting from json file.
SETTING_FILENAME = "vt_setting.json"
SETTINGS.update(load_json(SETTING_FILENAME))


def get_settings(prefix: str = ""):
    prefix_length = len(prefix)
    return {k[prefix_length:]: v for k, v in SETTINGS.items() if k.startswith(prefix)}
