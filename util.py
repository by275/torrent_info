import ntpath
import re
import sys
from typing import Optional


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


def convert_torrent_info(torrent_info) -> dict:
    """from libtorrent torrent_info to python dictionary object"""
    try:
        import libtorrent as lt
    except ImportError as _e:
        raise ImportError("libtorrent package required") from _e

    return {
        "name": torrent_info.name(),
        "num_files": torrent_info.num_files(),
        "total_size": torrent_info.total_size(),  # in byte
        "total_size_fmt": size_fmt(torrent_info.total_size()),  # in byte
        "info_hash": str(torrent_info.info_hash()),  # original type: libtorrent.sha1_hash
        "num_pieces": torrent_info.num_pieces(),
        "creator": torrent_info.creator() or f"libtorrent v{lt.version}",
        "comment": torrent_info.comment(),
        "files": [
            {"path": file.path, "size": file.size, "size_fmt": size_fmt(file.size)} for file in torrent_info.files()
        ],
        "magnet_uri": lt.make_magnet_uri(torrent_info),
    }
