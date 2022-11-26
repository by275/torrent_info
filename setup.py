__menu = {
    "uri": __package__,
    "name": "토렌트 정보",
    "list": [
        {
            "uri": "search",
            "name": "검색",
        },
        {
            "uri": "setting",
            "name": "설정",
        },
        {
            "uri": "log",
            "name": "로그",
        },
    ],
}

setting = {
    "filepath": __file__,
    "use_db": True,
    "use_default_setting": True,
    "home_module": "search",
    "menu": __menu,
    "setting_menu": None,
    "default_route": "single",
}

# pylint: disable=import-error
from plugin import create_plugin_instance

P = create_plugin_instance(setting)

from .logic import LogicMain

P.set_module_list([LogicMain])
