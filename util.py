import ntpath
import re
import sys
import time
from typing import Optional, List
from urllib.parse import urlparse

# local
from .setup import P

logger = P.logger


os_mode = None  # Can be 'windows', 'mac', 'linux' or None. None will auto-detect os.
# Replacement order is important, don't use dicts to store
platform_replaces = {
    "windows": [
        ['[:*?"<>| ]+', " "],  # Turn illegal characters into a space
        [r"[\.\s]+([/\\]|$)", r"\1"],  # Dots cannot end file or directory names
    ],
    "mac": [["[: ]+", " "]],  # Only colon is illegal here
    "linux": [],  # No illegal chars
}


def pathscrub(dirty_path: str, os: Optional[str] = None, filename: bool = False) -> str:
    """
    Strips illegal characters for a given os from a path.
    :param dirty_path: Path to be scrubbed.
    :param os: Defines which os mode should be used, can be 'windows', 'mac', 'linux', or None to auto-detect
    :param filename: If this is True, path separators will be replaced with '-'
    :return: A valid path.
    """

    # See if global os_mode has been defined by pathscrub plugin
    if os_mode and not os:
        os = os_mode

    if not os:
        # If os is not defined, try to detect appropriate
        drive, path = ntpath.splitdrive(dirty_path)
        if sys.platform.startswith("win") or drive:
            os = "windows"
        elif sys.platform.startswith("darwin"):
            os = "mac"
        else:
            os = "linux"
    replaces = platform_replaces[os]

    # Make sure not to mess with windows drive specifications
    drive, path = ntpath.splitdrive(dirty_path)

    if filename:
        path = path.replace("/", " ").replace("\\", " ")
    for search, replace in replaces:
        path = re.sub(search, replace, path)
    # Remove spaces surrounding path components
    path = "/".join(comp.strip() for comp in path.split("/"))
    if os == "windows":
        path = "\\".join(comp.strip() for comp in path.split("\\"))
    path = path.strip()
    # If we stripped everything from a filename, complain
    if filename and dirty_path and not path:
        raise ValueError(f"Nothing was left after stripping invalid characters from path `{dirty_path}`!")
    return drive + path


def size_fmt(num: int, suffix: str = "B") -> str:
    # Windows에서 쓰는 단위로 가자 https://superuser.com/a/938259
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1000.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"


def convert_lt_info(lt_info) -> dict:
    """from libtorrent torrent_info to python dictionary object

    Reference:
    https://www.libtorrent.org/reference-Torrent_Info.html#torrent_info
    """

    import libtorrent as lt

    return {
        "name": lt_info.name(),
        "num_files": lt_info.num_files(),
        "total_size": lt_info.total_size(),  # in byte
        "total_size_fmt": size_fmt(lt_info.total_size()),  # in byte
        "info_hash": str(lt_info.info_hash()),  # original type: libtorrent.sha1_hash
        "num_pieces": lt_info.num_pieces(),
        "creator": lt_info.creator() or f"libtorrent v{lt.version}",
        "comment": lt_info.comment(),
        "files": [{"path": file.path, "size": file.size, "size_fmt": size_fmt(file.size)} for file in lt_info.files()],
        "magnet_uri": lt.make_magnet_uri(lt_info),
    }


def get_metadata(handle, timeout: int = 15, n_try: int = 3):
    """retrieve libtorrent (torrent_info and torrent_status) from handle"""
    max_try = max(n_try, 1)
    for tryid in range(max_try):
        timeleft = timeout
        logger.debug("Trying to get metadata... %d/%d", tryid + 1, max_try)
        while not handle.has_metadata():
            time.sleep(0.1)
            timeleft -= 0.1
            if timeleft <= 0:
                break

        if handle.has_metadata():
            lt_info = handle.get_torrent_info()
            logger.debug("Successfully got metadata after %d*%d+%.2f seconds", tryid, timeout, timeout - timeleft)
            break
        if tryid + 1 == max_try:
            raise TimeoutError(f"Timed out after {max_try}*{timeout} seconds")

    # peerinfo if possible
    if handle.status(0).num_complete >= 0:
        return lt_info, handle.status(0)
    return lt_info, None


def get_lt_params(magnet_uri: str, trackers: List[str] = None):
    """from magnet uri to add_torrent_params

    Reference:
    https://www.libtorrent.org/reference-Core.html#parse_magnet_uri()
    https://www.libtorrent.org/reference-Add_Torrent.html#add_torrent_params
    """

    import libtorrent as lt

    # default arguments
    if trackers is None:
        trackers = []

    # parameters
    params = lt.parse_magnet_uri(magnet_uri)

    # prevent downloading
    # https://stackoverflow.com/q/45680113
    if isinstance(params, dict):
        params["flags"] |= lt.add_torrent_params_flags_t.flag_upload_mode
    else:
        params.flags |= lt.add_torrent_params_flags_t.flag_upload_mode

    lt_version = [int(v) for v in lt.version.split(".")]
    if [0, 16, 13, 0] < lt_version < [1, 1, 3, 0]:
        # for some reason the info_hash needs to be bytes but it's a struct called sha1_hash
        if isinstance(params, dict):
            params["info_hash"] = params["info_hash"].to_bytes()
        else:
            params.info_hash = params.info_hash.to_bytes()

    # add trackers if none in params
    if isinstance(params, dict):
        if len(params["trackers"]) == 0:
            params["trackers"] = trackers
    else:
        if len(params.trackers) == 0:
            params.trackers = trackers

    return params


def get_lt_session(use_dht: bool = False, http_proxy: str = None):
    """returns libtorrent session from settings_pack

    Reference:
    https://www.libtorrent.org/reference-Settings.html#settings_pack
    https://www.libtorrent.org/reference-Session.html#session
    """

    import libtorrent as lt

    settings = {
        # basics
        # 'user_agent': 'libtorrent/' + lt.__version__,
        "listen_interfaces": "0.0.0.0:6881",
        # dht
        "enable_dht": use_dht,
        "use_dht_as_fallback": True,
        "dht_bootstrap_nodes": "router.bittorrent.com:6881,dht.transmissionbt.com:6881,router.utorrent.com:6881,127.0.0.1:6881",
        "enable_lsd": False,
        "enable_upnp": True,
        "enable_natpmp": True,
        "announce_to_all_tiers": True,
        "announce_to_all_trackers": True,
        "aio_threads": 4 * 2,
        "checking_mem_usage": 1024 * 2,
    }
    if http_proxy:
        proxy_url = urlparse(http_proxy)
        settings.update(
            {
                "proxy_username": proxy_url.username,
                "proxy_password": proxy_url.password,
                "proxy_hostname": proxy_url.hostname,
                "proxy_port": proxy_url.port,
                "proxy_type": lt.proxy_type_t.http_pw
                if proxy_url.username and proxy_url.password
                else lt.proxy_type_t.http,
                "force_proxy": True,
                "anonymous_mode": True,
            }
        )
    session = lt.session(settings)

    session.add_extension("ut_metadata")
    session.add_extension("ut_pex")
    session.add_extension("metadata_transfer")
    return session
