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
