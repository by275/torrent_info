import json
import os
import platform
import shlex
from datetime import datetime
from urllib.parse import quote

# third-party
import requests
from flask import Response, jsonify, render_template
from sqlitedict import SqliteDict
from werkzeug.exceptions import MethodNotAllowed

# pylint: disable=import-error
from plugin import F, PluginModuleBase
from tool import ToolModalCommand

# local
from .util import LibTorrent
from .setup import P

plugin = P
logger = plugin.logger
package_name = plugin.package_name
ModelSetting = plugin.ModelSetting
plugin_info = plugin.plugin_info


class LogicMain(PluginModuleBase):
    db_default = {
        "use_dht": "False",
        "timeout": "15",
        "n_try": "3",
        "http_proxy": "",
        "pagesize": "20",
        "trackers": "",
        "tracker_last_update": "1970-01-01",
        "tracker_update_every": "30",
        "tracker_update_from": "best",
        "libtorrent_build": "191217",
    }

    torrent_cache = None

    tracker_update_from_list = ["best", "all", "all_udp", "all_http", "all_https", "all_ws", "best_ip", "all_ip"]

    def __init__(self, PM):
        super().__init__(PM, None)

    def plugin_load(self):
        try:
            # 토렌트 캐쉬 초기화
            self.cache_init()

            # libtorrent 자동 설치
            new_build = int(plugin_info["libtorrent_build"].rsplit("-", maxsplit=1)[-1])
            installed_build = ModelSetting.get_int("libtorrent_build")
            if (new_build > installed_build) or (not self.is_installed()):
                self.install(show_modal=False)

            # tracker 자동 업데이트
            tracker_update_every = ModelSetting.get_int("tracker_update_every")
            tracker_last_update = ModelSetting.get("tracker_last_update")
            if tracker_update_every > 0:
                if (datetime.now() - datetime.strptime(tracker_last_update, "%Y-%m-%d")).days >= tracker_update_every:
                    self.update_tracker()
        except Exception:
            logger.exception("Exception on plugin load:")

    def process_menu(self, sub, req):
        arg = ModelSetting.to_dict()
        arg["package_name"] = package_name
        if sub == "setting":
            arg["trackers"] = "\n".join(json.loads(arg["trackers"]))
            arg["tracker_update_from_list"] = [
                [x, f"https://ngosang.github.io/trackerslist/trackers_{x}.txt"] for x in self.tracker_update_from_list
            ]
            arg["plugin_ver"] = plugin_info["version"]

            # api usage
            base_api = F.SystemModelSetting.get("ddns") + f"/{package_name}/api"
            excmds = ["curl", "-X", "POST", "-H", "Content-Type: application/json"]
            arg["m2i_api"] = shlex.join(
                excmds + [f"{base_api}/m2i", "-d", json.dumps({"apikey": "APIKEY", "uri": "MAGNET_URI"})]
            )
            arg["t2i_api"] = shlex.join(
                excmds + [f"{base_api}/t2i", "-d", json.dumps({"apikey": "APIKEY", "url": "TORRENT_URL"})]
            )
            excmds += ["-o", "filename.torrent"]
            arg["m2t_api"] = shlex.join(
                excmds + [f"{base_api}/m2t", "-d", json.dumps({"apikey": "APIKEY", "uri": "MAGNET_URI"})]
            )
        elif sub == "search":
            arg["cache_size"] = len(self.torrent_cache)
        try:
            return render_template(f"{package_name}_{sub}.html", arg=arg)
        except Exception:
            return render_template("sample.html", title=f"{package_name} - {sub}")

    def process_ajax(self, sub, req):
        if sub == "install":
            return jsonify(self.install())
        if sub == "is_installed":
            is_installed = self.is_installed()
            return jsonify({"installed": bool(is_installed), "version": is_installed})
        if sub == "uninstall":
            return jsonify(self.uninstall())

        try:
            if sub == "cache":
                p = req.form.to_dict() if req.method == "POST" else req.args.to_dict()
                action = p.get("action", "")
                infohash = p.get("infohash", "")
                name = p.get("name", "")
                if action == "clear":
                    self.torrent_cache.clear()
                elif action == "delete" and infohash:
                    for h in infohash.split(","):
                        if h and h in self.torrent_cache:
                            del self.torrent_cache[h]
                # filtering
                if name:
                    info = (val["info"] for val in self.torrent_cache.values() if name.strip() in val["info"]["name"])
                elif infohash:
                    info = (self.torrent_cache[h]["info"] for h in infohash.split(",") if h and h in self.torrent_cache)
                else:
                    info = (val["info"] for val in self.torrent_cache.values())
                info = sorted(info, key=lambda x: x["creation_date"], reverse=True)
                total = len(info)
                if p.get("c", ""):
                    counter = int(p.get("c"))
                    pagesize = ModelSetting.get_int("pagesize")
                    if counter == 0:
                        info = info[:pagesize]
                    elif counter == len(info):
                        info = []
                    else:
                        info = info[counter : counter + pagesize]
                # return
                if action == "list":
                    return jsonify({"success": True, "info": info, "total": total})
                return jsonify({"success": True, "count": len(info)})
            if sub == "tracker_update":
                self.update_tracker()
                return jsonify({"success": True})
            if sub == "tracker_save":
                self.tracker_save(req)
                return jsonify({"success": True})
            # if sub == "torrent_info":
            #     # for global use - default arguments by function itself
            #     try:
            #         from torrent_info import Logic as TorrentInfoLogic

            #         data = req.form["hash"]
            #         logger.debug(data)
            #         if data.startswith("magnet"):
            #             ret = TorrentInfoLogic.parse_magnet_uri(data)
            #         else:
            #             ret = TorrentInfoLogic.parse_torrent_url(data)
            #         return jsonify(ret)
            #     except Exception as e:
            #         logger.error("Exception:%s", e)
            #         logger.error(traceback.format_exc())
            if sub == "get_torrent_info":
                # for local use - default arguments from user db
                if req.form["uri_url"].startswith("magnet"):
                    torrent_info = self.parse_magnet_uri(req.form["uri_url"])
                else:
                    torrent_info = self.parse_torrent_url(req.form["uri_url"])
                return jsonify({"success": True, "info": torrent_info})
            if sub == "get_file_info":
                fs = req.files["file"]
                fs.seek(0)
                torrent_file = fs.read()
                torrent_info = self.parse_torrent_file(torrent_file)
                return jsonify({"success": True, "info": torrent_info})
            if sub == "get_torrent_file" and req.method == "GET":
                data = req.args.to_dict()
                magnet_uri = data.get("uri", "")
                if not magnet_uri.startswith("magnet"):
                    magnet_uri = "magnet:?xt=urn:btih:" + magnet_uri
                return self.parse_magnet_uri(magnet_uri, no_cache=True, to_torrent=True)
        except Exception as e:
            logger.exception("Exception while processing ajax requests:")
            return jsonify({"success": False, "log": str(e)})

    def process_api(self, sub, req):
        try:
            # only allow -X POST -H 'Content-Type: application/json'
            if req.method != "POST":
                raise MethodNotAllowed(valid_methods=["POST"])
            _d = req.get_json()

            uri = _d.get("uri", "")
            url = _d.get("url", "")

            if sub == "m2i":
                if uri:
                    if not uri.startswith("magnet"):
                        uri = "magnet:?xt=urn:btih:" + uri

                    # override db default by api input
                    func_args = {k: _d[k] for k in ["use_dht", "no_cache", "timeout", "n_try"] if k in _d}

                    info = self.parse_magnet_uri(uri, **func_args)
                    return jsonify({"success": True, "info": info})
                return jsonify({"success": False, "log": "missing parameter: 'uri'"})

            if sub == "t2i":
                if url:
                    info = self.parse_torrent_url(_d.get("url"))
                    return jsonify({"success": True, "info": info})
                return jsonify({"success": False, "log": "missing parameter: 'url'"})

            if sub == "m2t":
                if uri:
                    if not uri.startswith("magnet"):
                        uri = "magnet:?xt=urn:btih:" + uri

                    # override db default by api input
                    func_args = {k: _d[k] for k in ["use_dht", "timeout", "n_try"] if k in _d}

                    return self.parse_magnet_uri(uri, no_cache=True, to_torrent=True, **func_args)
                return jsonify({"success": False, "log": "missing parameter: 'uri'"})
        except Exception as e:
            logger.exception("Exception while processing api requests:")
            return jsonify({"success": False, "log": str(e)})

    def cache_init(self):
        if self.torrent_cache is None:
            db_file = os.path.join(F.config["path_data"], "db", f"{package_name}.db")
            self.torrent_cache = SqliteDict(
                db_file, tablename=f"{package_name}_cache", encode=json.dumps, decode=json.loads, autocommit=True
            )

    def tracker_save(self, req):
        for key, value in req.form.items():
            logger.debug({"key": key, "value": value})
            if key == "trackers":
                value = json.dumps(value.split("\n"))
            logger.debug("Key:%s Value:%s", key, value)
            entity = F.db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            entity.value = value
        F.db.session.commit()

    def update_tracker(self):
        # https://github.com/ngosang/trackerslist
        src_url = f"https://ngosang.github.io/trackerslist/trackers_{ModelSetting.get('tracker_update_from')}.txt"
        new_trackers = requests.get(src_url).content.decode("utf8").split("\n\n")[:-1]
        ModelSetting.set("trackers", json.dumps(new_trackers))
        ModelSetting.set("tracker_last_update", datetime.now().strftime("%Y-%m-%d"))

    def is_installed(self) -> str:
        try:
            import libtorrent as lt
        except ImportError:
            return ""
        else:
            return lt.version

    def install(self, show_modal: bool = True) -> dict:
        try:
            # platform check - whitelist
            if platform.system() == "Linux" and F.config["running_type"] == "docker":
                install_sh = os.path.join(os.path.dirname(__file__), "install.sh")
                commands = [
                    ["msg", "잠시만 기다려주세요."],
                    ["chmod", "+x", install_sh],
                    [install_sh, "-delete"],
                    [install_sh, plugin_info["libtorrent_build"]],
                    ["msg", "완료되었습니다."],
                ]
                ToolModalCommand.start("libtorrent 설치", commands, wait=True, show_modal=show_modal, clear=True)
                return {"success": True}
            return {"succes": False, "log": "지원하지 않는 시스템입니다."}
        except Exception as e:
            logger.exception("Exception while attempting install:")
            return {"success": False, "log": str(e)}

    def uninstall(self) -> dict:
        try:
            if platform.system() == "Linux" and F.config["running_type"] == "docker":
                install_sh = os.path.join(os.path.dirname(__file__), "install.sh")
                commands = [
                    ["msg", "잠시만 기다려주세요."],
                    ["chmod", "+x", install_sh],
                    [install_sh, "-delete"],
                    ["msg", "완료되었습니다."],
                ]
                ToolModalCommand.start("libtorrent 삭제", commands, wait=True, show_modal=True, clear=True)
                return {"success": True}
            return {"succes": False, "log": "지원하지 않는 시스템입니다."}
        except Exception as e:
            logger.exception("Exception while attempting uninstall:")
            return {"success": False, "log": str(e)}

    def parse_magnet_uri(
        self,
        magnet_uri,
        use_dht=None,
        timeout=None,
        trackers=None,
        no_cache=False,
        n_try=None,
        to_torrent=False,
        http_proxy=None,
    ):
        # default function arguments from db
        if use_dht is None:
            use_dht = ModelSetting.get_bool("use_dht")
        if timeout is None:
            timeout = ModelSetting.get_int("timeout")
        if trackers is None:
            trackers = json.loads(ModelSetting.get("trackers"))
        if n_try is None:
            n_try = ModelSetting.get_int("n_try")
        if http_proxy is None:
            http_proxy = ModelSetting.get("http_proxy")

        # parameters
        torrent = LibTorrent.parse_magnet_uri(magnet_uri, trackers=trackers)

        # 캐시에 있으면...
        self.cache_init()
        if (not no_cache) and (torrent.info_hash in self.torrent_cache):
            return self.torrent_cache[torrent.info_hash]["info"]

        info = torrent.get_metadata(use_dht=use_dht, http_proxy=http_proxy, timeout=timeout, n_try=n_try).to_dict()

        # caching for later use
        self.cache_init()
        self.torrent_cache[info["info_hash"]] = {
            "info": info,
        }
        if to_torrent:
            torrent_file, torrent_name = torrent.to_file()
            resp = Response(torrent_file)
            resp.headers["Content-Type"] = "application/x-bittorrent"
            resp.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(torrent_name + ".torrent")
            return resp
        return info

    def parse_torrent_file(self, torrent_file: bytes) -> dict:
        info = LibTorrent.from_torrent_file(torrent_file).to_dict()

        # caching for later use
        self.cache_init()
        self.torrent_cache[info["info_hash"]] = {
            "info": info,
        }
        return info

    def parse_torrent_url(self, url: str, http_proxy: str = None) -> dict:
        if http_proxy is None:
            http_proxy = ModelSetting.get("http_proxy")
        proxies = {"http": http_proxy, "https": http_proxy} if http_proxy else None
        return self.parse_torrent_file(requests.get(url, proxies=proxies).content)
