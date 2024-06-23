import ntpath
import re
import sys
import time
from copy import copy
from datetime import datetime
from timeit import default_timer as timer
from typing import Dict, List, Optional, Tuple
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


class LibTorrent:
    """wrapper class of libtorrent to obtain torrent metadata without downloading"""

    # from libtorrent
    lt_atp = None  # add_torrent_params
    lt_settings: dict = {
        # basics
        # 'user_agent': 'libtorrent/' + lt.__version__,
        "listen_interfaces": "0.0.0.0:6881",
        # dht
        "enable_dht": False,
        "use_dht_as_fallback": True,
        "dht_bootstrap_nodes": "router.bittorrent.com:6881,dht.transmissionbt.com:6881,router.utorrent.com:6881,127.0.0.1:6881",
        "enable_lsd": False,
        "enable_upnp": True,
        "enable_natpmp": True,
        "announce_to_all_tiers": True,
        "announce_to_all_trackers": True,
        "aio_threads": 4 * 2,
        "checking_mem_usage": 1024 * 2,
    }  # settings_pack
    lt_dict: Dict[bytes, str] = None  # torrent dict
    lt_info = None  # torrent info

    # for internal use
    info_hash: str = None
    info_plus: dict = None

    def to_dict(self) -> dict:
        """from libtorrent torrent_info to python dictionary object

        Reference:
        https://www.libtorrent.org/reference-Torrent_Info.html#torrent_info
        """

        import libtorrent as lt  # pylint: disable=import-error

        _dict = {
            "name": self.lt_info.name(),
            "num_files": self.lt_info.num_files(),
            "total_size": self.lt_info.total_size(),  # in byte
            "total_size_fmt": size_fmt(self.lt_info.total_size()),  # in byte
            "info_hash": str(self.lt_info.info_hash()),  # original type: libtorrent.sha1_hash
            "num_pieces": self.lt_info.num_pieces(),
            "creator": self.lt_info.creator() or f"libtorrent v{lt.version}",
            "comment": self.lt_info.comment(),
            "files": [
                {"path": file.path, "size": file.size, "size_fmt": size_fmt(file.size)} for file in self.lt_info.files()
            ],
            "magnet_uri": lt.make_magnet_uri(self.lt_info),
        }
        if self.info_plus is not None:
            _dict.update(self.info_plus)
        return _dict

    def to_file(self) -> Tuple[bytes, str]:
        import libtorrent as lt  # pylint: disable=import-error

        _file = lt.bencode(self.lt_dict)
        _name = pathscrub(self.lt_info.name(), os="windows", filename=True)
        return _file, _name

    @classmethod
    def from_torrent_file(cls, torrent_file: bytes):
        """returns an instance of LibTorrent object with instance variables from torrent_file

        Data conversion flow:
        torrent_file >> lt_dict >> lt_info + info_plus
        """

        import libtorrent as lt  # pylint: disable=import-error

        _dict = lt.bdecode(torrent_file)
        _plus = {
            "trackers": [x[0].decode("utf-8") for x in _dict.get(b"announce-list", [])],
            "creation_date": datetime.fromtimestamp(_dict.get(b"creation date", 0)).isoformat(),
        }
        _info = lt.torrent_info(_dict)

        _t = cls()
        _t.lt_dict = _dict
        _t.info_plus = _plus
        _t.lt_info = _info
        _t.info_hash = str(_info.info_hash())
        return _t

    @classmethod
    def parse_magnet_uri(cls, uri: str, trackers: List[str] = None):
        """parse magnet uri to generate add_torrent_params and get ready for retrieving metadata

        Reference:
        https://www.libtorrent.org/reference-Core.html#parse_magnet_uri()
        https://www.libtorrent.org/reference-Add_Torrent.html#add_torrent_params
        """

        import libtorrent as lt  # pylint: disable=import-error

        # default arguments
        if trackers is None:
            trackers = []

        # parameters
        atp = lt.parse_magnet_uri(uri)

        # https://gist.github.com/francoism90/4db9efa5af546d831ca47208e58f3364
        atp.storage_mode = lt.storage_mode_t.storage_mode_sparse
        atp.flags |= lt.torrent_flags.duplicate_is_error | lt.torrent_flags.auto_managed | lt.torrent_flags.upload_mode

        # add trackers if none in atp
        if len(atp.trackers) == 0:
            atp.trackers = trackers

        _t = cls()
        _t.lt_atp = atp
        _t.info_hash = str(atp["info_hash"] if isinstance(atp, dict) else atp.info_hash)
        return _t

    @staticmethod
    def _get_metadata(handle, timeout: int = 15, n_try: int = 3):
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
                _info = handle.get_torrent_info()
                logger.debug("Successfully got metadata after %d*%d+%.2f seconds", tryid, timeout, timeout - timeleft)
                break
            if tryid + 1 == max_try:
                raise TimeoutError(f"Timed out after {max_try}*{timeout} seconds")

        # peerinfo if possible
        if handle.status(0).num_complete >= 0:
            return _info, handle.status(0)
        return _info, None

    def get_metadata(self, use_dht: bool = False, http_proxy: str = None, timeout: int = 15, n_try: int = 3):
        """generate libtorrent session from settings_pack

        Reference:
        https://www.libtorrent.org/reference-Settings.html#settings_pack
        https://www.libtorrent.org/reference-Session.html#session
        """

        import libtorrent as lt  # pylint: disable=import-error

        # settings
        settings = copy(self.lt_settings)
        settings["enable_dht"] = use_dht
        if http_proxy:
            proxy_url = urlparse(http_proxy)
            settings.update(
                {
                    "proxy_username": proxy_url.username,
                    "proxy_password": proxy_url.password,
                    "proxy_hostname": proxy_url.hostname,
                    "proxy_port": proxy_url.port,
                    "proxy_type": (
                        lt.proxy_type_t.http_pw if proxy_url.username and proxy_url.password else lt.proxy_type_t.http
                    ),
                    "force_proxy": True,
                    "anonymous_mode": True,
                }
            )

        # session
        sess = lt.session(settings)

        sess.add_extension("ut_metadata")
        sess.add_extension("ut_pex")
        sess.add_extension("metadata_transfer")

        # handle
        h = sess.add_torrent(self.lt_atp)

        if use_dht:
            h.force_dht_announce()

        try:
            stime = timer()
            _info, _status = LibTorrent._get_metadata(h, timeout=timeout, n_try=n_try)
            etime = timer() - stime
        finally:
            sess.remove_torrent(h, True)

        # create torrent object and generate file stream
        torrent = lt.create_torrent(_info)
        torrent.set_creator(f"libtorrent v{lt.version}")  # signature
        _dict = torrent.generate()

        # additional info
        atp = self.lt_atp
        _plus = {
            "trackers": atp.trackers if not isinstance(atp, dict) else atp["trackers"],
            "creation_date": datetime.fromtimestamp(_dict[b"creation date"]).isoformat(),
            "elapsed_time": etime,
        }

        # peerinfo if possible
        if _status is not None:
            _plus.update(
                {
                    "seeders": _status.num_complete,
                    "peers": _status.num_incomplete,
                }
            )
        self.lt_dict = _dict
        self.info_plus = _plus
        self.lt_info = _info
        self.info_hash = str(_info.info_hash())
        return self
