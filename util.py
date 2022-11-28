import ntpath
import re
import sys
import time
from typing import Optional

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
    """from libtorrent torrent_info to python dictionary object"""
    try:
        import libtorrent as lt
    except ImportError as e:
        raise ImportError("libtorrent package required") from e

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


def get_metadata(handle, timeout=None, n_try=None):
    """retrieve libtorrent (torrent_info and torrent_status) from handle"""
    max_try = max(n_try, 1)
    for tryid in range(max_try):
        timeout_value = timeout
        logger.debug("Trying to get metadata... %d/%d", tryid + 1, max_try)
        while not handle.has_metadata():
            time.sleep(0.1)
            timeout_value -= 0.1
            if timeout_value <= 0:
                break

        if handle.has_metadata():
            lt_info = handle.get_torrent_info()
            logger.debug("Successfully got metadata after %d*%d+%.2f seconds", tryid, timeout, timeout - timeout_value)
            break
        if tryid + 1 == max_try:
            raise TimeoutError(f"Timed out after {max_try}*{timeout} seconds")

    # peerinfo if possible
    if handle.status(0).num_complete >= 0:
        return lt_info, handle.status(0)
    return lt_info, None
