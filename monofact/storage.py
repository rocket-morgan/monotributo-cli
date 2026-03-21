from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  env TEXT NOT NULL,
  cuit TEXT NOT NULL,
  pto_vta INTEGER NOT NULL,
  tipo_comp INTEGER NOT NULL,
  cbte_nro INTEGER,
  doc_tipo INTEGER NOT NULL,
  doc_nro TEXT NOT NULL,
  cbte_fch TEXT NOT NULL,
  imp_total REAL NOT NULL,
  resultado TEXT,
  cae TEXT,
  cae_vto TEXT,
  obs_json TEXT,
  errors_json TEXT,
  request_json TEXT,
  response_json TEXT,
  fingerprint TEXT
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def save_invoice(conn: sqlite3.Connection, payload: dict[str, Any], result: dict[str, Any]) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO invoices (
          env,cuit,pto_vta,tipo_comp,cbte_nro,doc_tipo,doc_nro,cbte_fch,imp_total,
          resultado,cae,cae_vto,obs_json,errors_json,request_json,response_json,fingerprint
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payload.get("env"),
            str(payload.get("cuit")),
            int(payload.get("pto_vta")),
            int(payload.get("tipo_comp")),
            result.get("cbte_nro"),
            int(payload.get("doc_tipo")),
            str(payload.get("doc_nro")),
            str(payload.get("cbte_fch")),
            float(payload.get("imp_total")),
            result.get("resultado"),
            result.get("cae"),
            result.get("cae_vto"),
            json.dumps(result.get("obs", []), ensure_ascii=False),
            json.dumps(result.get("errors", []), ensure_ascii=False),
            json.dumps(payload, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            result.get("fingerprint"),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "record_id": int(row["id"]),
        "created_at": row["created_at"],
        "env": row["env"],
        "pto_vta": int(row["pto_vta"]),
        "tipo_comp": int(row["tipo_comp"]),
        "cbte_nro": int(row["cbte_nro"]) if row["cbte_nro"] is not None else None,
        "cbte_fch": row["cbte_fch"],
        "doc_tipo": int(row["doc_tipo"]),
        "doc_nro": row["doc_nro"],
        "imp_total": row["imp_total"],
        "resultado": row["resultado"],
        "cae": row["cae"],
    }


def _row_to_detail(row: sqlite3.Row) -> dict[str, Any]:
    detail = _row_to_summary(row)
    detail.update({
        "cuit": row["cuit"],
        "cae_vto": row["cae_vto"],
        "obs": _loads_json(row["obs_json"], []),
        "errors": _loads_json(row["errors_json"], []),
        "request": _loads_json(row["request_json"], {}),
        "response": _loads_json(row["response_json"], {}),
        "fingerprint": row["fingerprint"],
    })
    return detail


def list_invoices_by_cbte_nro(
    conn: sqlite3.Connection,
    *,
    env: str,
    pto_vta: int,
    tipo_comp: int,
    cbte_nro: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM invoices
        WHERE env = ? AND pto_vta = ? AND tipo_comp = ? AND cbte_nro = ?
        ORDER BY created_at DESC, id DESC
        """,
        (env, pto_vta, tipo_comp, cbte_nro),
    ).fetchall()
    return [_row_to_summary(row) for row in rows]


def list_invoices_by_date_range(
    conn: sqlite3.Connection,
    *,
    env: str,
    pto_vta: int,
    tipo_comp: int,
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM invoices
        WHERE env = ? AND pto_vta = ? AND tipo_comp = ? AND cbte_fch BETWEEN ? AND ?
        ORDER BY cbte_fch ASC, cbte_nro ASC, id ASC
        """,
        (env, pto_vta, tipo_comp, date_from, date_to),
    ).fetchall()
    return [_row_to_summary(row) for row in rows]


def get_invoice_by_cbte_nro(
    conn: sqlite3.Connection,
    *,
    env: str,
    pto_vta: int,
    tipo_comp: int,
    cbte_nro: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM invoices
        WHERE env = ? AND pto_vta = ? AND tipo_comp = ? AND cbte_nro = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (env, pto_vta, tipo_comp, cbte_nro),
    ).fetchone()
    if row is None:
        return None
    return _row_to_detail(row)
