import pathlib
from datetime import datetime

from dataclasses_json import global_config


def register_path_type(path_type):

    def path_encoder(path: pathlib.Path) -> str | None:
        return str(path) if path is not None else None

    def path_decoder(path_str: str) -> pathlib.Path | None:
        return pathlib.Path(path_str) if path_str is not None else None

    global_config.encoders[path_type] = path_encoder
    global_config.decoders[path_type] = path_decoder


register_path_type(pathlib.Path)
register_path_type(pathlib.WindowsPath)
register_path_type(pathlib.PosixPath)
register_path_type(pathlib.PurePath)
register_path_type(pathlib.PureWindowsPath)
register_path_type(pathlib.PurePosixPath)

global_config.encoders[datetime] = lambda dt: dt.isoformat()
global_config.decoders[datetime] = lambda dt_s: datetime.fromisoformat(dt_s) if dt_s not in [None, str(None)] else None
