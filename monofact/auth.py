from __future__ import annotations

import configparser
import contextlib
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class AuthProfile:
    profile_name: str
    ini_path: Path
    cert_path: Path
    key_path: Path
    wsaa_url: str
    cacert: str
    cache_dir: Path


@dataclass(frozen=True)
class AuthCredentials:
    token: str
    sign: str
    source: str
    expiration_time: str | None
    ta_path: Path | None
    profile_name: str | None = None


def _normalize_manual_credentials(token: str, sign: str) -> tuple[str, str]:
    token = token.strip()
    sign = sign.strip()
    if _looks_like_file_reference(token) and _looks_like_file_reference(sign):
        return "", ""
    return token, sign


def inspect_auth(settings: Settings) -> tuple[str, str | None]:
    token, sign = _normalize_manual_credentials(settings.token, settings.sign)
    if token and sign:
        return "manual", None
    if token or sign:
        raise AuthError("MONOFACT_TOKEN y MONOFACT_SIGN deben venir juntos")
    profile = load_pyafipws_profile(settings)
    return "pyafipws", profile.profile_name


def resolve_auth_credentials(settings: Settings, force_refresh: bool = False) -> AuthCredentials:
    token, sign = _normalize_manual_credentials(settings.token, settings.sign)
    if token and sign:
        return AuthCredentials(
            token=token,
            sign=sign,
            source="manual",
            expiration_time=None,
            ta_path=None,
        )
    if token or sign:
        raise AuthError("MONOFACT_TOKEN y MONOFACT_SIGN deben venir juntos")

    profile = load_pyafipws_profile(settings)
    ta_path = _ta_path("wsfe", profile.cert_path, profile.key_path, profile.cache_dir)
    if force_refresh and ta_path.exists():
        ta_path.unlink()

    wsaa_cls = _get_wsaa_class()
    wsaa = wsaa_cls()
    wsaa.LanzarExcepciones = True
    with contextlib.redirect_stdout(io.StringIO()):
        wsaa.Autenticar(
            "wsfe",
            str(profile.cert_path),
            str(profile.key_path),
            profile.wsaa_url,
            None,
            "httplib2",
            profile.cacert,
            cache=str(profile.cache_dir),
        )

    expiration_time = None
    try:
        expiration_time = wsaa.ObtenerTagXml("expirationTime")
    except Exception:
        expiration_time = None

    return AuthCredentials(
        token=wsaa.Token,
        sign=wsaa.Sign,
        source="pyafipws",
        expiration_time=expiration_time,
        ta_path=ta_path,
        profile_name=profile.profile_name,
    )


def load_pyafipws_profile(settings: Settings) -> AuthProfile:
    pyafipws_dir = Path(settings.pyafipws_dir).expanduser().resolve()
    if not pyafipws_dir.exists():
        raise AuthError(f"No existe MONOFACT_PYAFIPWS_DIR: {pyafipws_dir}")

    profile_name = "homologacion" if settings.env == "homo" else "produccion"
    ini_path = pyafipws_dir / "conf" / f"{profile_name}.ini"
    if not ini_path.is_file():
        raise AuthError(f"No existe configuración pyafipws para {settings.env}: {ini_path}")

    parser = configparser.ConfigParser()
    parser.read(ini_path)
    if not parser.has_section("WSAA"):
        raise AuthError(f"Falta sección [WSAA] en {ini_path}")

    cert_value = _get_required(parser, "WSAA", "CERT", ini_path)
    key_value = _get_required(parser, "WSAA", "PRIVATEKEY", ini_path)
    wsaa_url = parser.get("WSAA", "URL", fallback="").strip() or parser.get("WSAA", "WSDL", fallback="").strip()
    if not wsaa_url:
        raise AuthError(f"Falta URL/WSDL en {ini_path}")
    cacert = parser.get("WSAA", "CACERT", fallback="default").strip() or "default"

    cert_path = _resolve_repo_path(pyafipws_dir, cert_value)
    key_path = _resolve_repo_path(pyafipws_dir, key_value)
    for path in (cert_path, key_path):
        if not path.is_file():
            raise AuthError(f"No existe archivo requerido por pyafipws: {path}")

    cache_dir = pyafipws_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    return AuthProfile(
        profile_name=profile_name,
        ini_path=ini_path,
        cert_path=cert_path,
        key_path=key_path,
        wsaa_url=wsaa_url,
        cacert=cacert,
        cache_dir=cache_dir,
    )


def _get_required(parser: configparser.ConfigParser, section: str, option: str, ini_path: Path) -> str:
    value = parser.get(section, option, fallback="").strip()
    if not value:
        raise AuthError(f"Falta {option} en {ini_path}")
    return value


def _resolve_repo_path(pyafipws_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (pyafipws_dir / candidate).resolve()


def _looks_like_file_reference(value: str) -> bool:
    if not value:
        return False
    candidate = Path(value).expanduser()
    if candidate.exists():
        return True
    if any(sep in value for sep in ("/", "\\")):
        return True
    return False


def _ta_path(service: str, cert_path: Path, key_path: Path, cache_dir: Path) -> Path:
    digest = hashlib.md5((service + str(cert_path) + str(key_path)).encode("utf8")).hexdigest()
    return cache_dir / f"TA-{digest}.xml"


def _get_wsaa_class():
    from pyafipws.wsaa import WSAA

    return WSAA
