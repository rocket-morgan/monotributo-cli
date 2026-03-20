from __future__ import annotations

import os
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _default_pyafipws_dir() -> str:
    repo_family_dir = Path(__file__).resolve().parents[2]
    return str(repo_family_dir / "pyafipws")


@dataclass
class Settings:
    env: str
    cuit: int
    pto_vta: int
    tipo_comp_factura_c: int
    token: str
    sign: str
    db_path: str
    pyafipws_dir: str
    wsfe_homo: str
    wsfe_prod: str

    @property
    def wsfe_url(self) -> str:
        return self.wsfe_homo if self.env == "homo" else self.wsfe_prod


@lru_cache(maxsize=None)
def _load_dotenv_once(dotenv_path: str) -> None:
    load_dotenv(dotenv_path=dotenv_path, override=False)


def _autoload_dotenv() -> None:
    dotenv_path = str((Path.cwd() / ".env").resolve())
    _load_dotenv_once(dotenv_path)



def load_settings(
    env: str | None = None,
    cuit: int | None = None,
    pto_vta: int | None = None,
    tipo_comp: int | None = None,
    token: str | None = None,
    sign: str | None = None,
    db_path: str | None = None,
    pyafipws_dir: str | None = None,
) -> Settings:
    _autoload_dotenv()
    envv = env or os.getenv("MONOFACT_ENV", "homo")
    return Settings(
        env=envv,
        cuit=int(cuit if cuit is not None else os.getenv("MONOFACT_CUIT", "0")),
        pto_vta=int(pto_vta if pto_vta is not None else os.getenv("MONOFACT_PTO_VTA", "0")),
        tipo_comp_factura_c=int(tipo_comp if tipo_comp is not None else os.getenv("MONOFACT_TIPO_COMP_FACTURA_C", "11")),
        token=token if token is not None else os.getenv("MONOFACT_TOKEN", ""),
        sign=sign if sign is not None else os.getenv("MONOFACT_SIGN", ""),
        db_path=db_path or os.getenv("MONOFACT_DB_PATH", "./monofact.db"),
        pyafipws_dir=pyafipws_dir or os.getenv("MONOFACT_PYAFIPWS_DIR", _default_pyafipws_dir()),
        wsfe_homo=os.getenv("MONOFACT_WSFE_HOMO", "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"),
        wsfe_prod=os.getenv("MONOFACT_WSFE_PROD", "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"),
    )
