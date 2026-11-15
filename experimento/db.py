"""
experimento/db.py

Banco de dados (SQLite) do acompanhamento do experimento: leituras de solo,
decisoes diarias, acionamentos, clima do dia e medicoes de planta.

O caminho vem da variavel de ambiente DATABASE_PATH (padrao: data/experimento.db).
Em hospedagem com disco efemero (ex.: plano gratuito do Render) o arquivo e
perdido a cada reinicio; para o experimento real, use um disco persistente
ou rode o sistema localmente.
"""

import os
import sqlite3

GRUPOS = {
    "controle_a": "Controle A (tempo fixo)",
    "controle_b": "Controle B (limiar de umidade)",
    "experimental": "Experimental (ETc + clima + solo)",
}

CONFIG_PADRAO = {
    "latitude": "-22.4114",
    "longitude": "-47.5614",
    "elevation": "617",
    "area_m2": "0.25",
    "vazao_l_h": "120",
    "fase_cultura": "medio",
    "lamina_fixa_mm": "3.75",
    "chuva_observada_limiar_mm": "1.0",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grupo (
    codigo  TEXT PRIMARY KEY,
    nome    TEXT NOT NULL,
    n_vasos INTEGER NOT NULL DEFAULT 3 CHECK (n_vasos > 0)
);
CREATE TABLE IF NOT EXISTS leitura_solo (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo       TEXT NOT NULL REFERENCES grupo(codigo),
    ts          TEXT NOT NULL,
    umidade_pct REAL NOT NULL CHECK (umidade_pct BETWEEN 0 AND 100),
    origem      TEXT NOT NULL DEFAULT 'sensor'
);
CREATE INDEX IF NOT EXISTS idx_leitura_grupo_ts ON leitura_solo (grupo, ts);
CREATE TABLE IF NOT EXISTS decisao (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo        TEXT NOT NULL REFERENCES grupo(codigo),
    data         TEXT NOT NULL,
    ts           TEXT NOT NULL,
    irrigar      INTEGER NOT NULL,
    codigo       TEXT NOT NULL,
    motivo       TEXT NOT NULL,
    volume_l     REAL NOT NULL,
    duracao_min  REAL NOT NULL,
    umidade_solo REAL,
    eto_mm_dia   REAL,
    etc_mm_dia   REAL,
    prob_chuva   REAL,
    UNIQUE (grupo, data)
);
CREATE TABLE IF NOT EXISTS acionamento (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo       TEXT NOT NULL REFERENCES grupo(codigo),
    ts          TEXT NOT NULL,
    volume_l    REAL NOT NULL CHECK (volume_l >= 0),
    duracao_min REAL
);
CREATE TABLE IF NOT EXISTS clima_dia (
    data                TEXT PRIMARY KEY,
    prob_chuva_prevista REAL,
    chuva_observada_mm  REAL,
    fonte_observada     TEXT
);
CREATE TABLE IF NOT EXISTS medicao_planta (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo          TEXT NOT NULL REFERENCES grupo(codigo),
    vaso           INTEGER NOT NULL CHECK (vaso > 0),
    data           TEXT NOT NULL,
    altura_cm      REAL CHECK (altura_cm IS NULL OR altura_cm >= 0),
    n_folhas       INTEGER CHECK (n_folhas IS NULL OR n_folhas >= 0),
    massa_fresca_g REAL CHECK (massa_fresca_g IS NULL OR massa_fresca_g >= 0),
    massa_seca_g   REAL CHECK (massa_seca_g IS NULL OR massa_seca_g >= 0),
    UNIQUE (grupo, vaso, data)
);
"""


def caminho_db():
    padrao = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "experimento.db")
    return os.environ.get("DATABASE_PATH", padrao)


def conectar(caminho=None):
    caminho = caminho or caminho_db()
    if caminho != ":memory:":
        pasta = os.path.dirname(caminho)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    iniciar(con)
    return con


def iniciar(con):
    con.executescript(SCHEMA)
    for codigo, nome in GRUPOS.items():
        con.execute("INSERT OR IGNORE INTO grupo (codigo, nome) VALUES (?, ?)", (codigo, nome))
    for chave, valor in CONFIG_PADRAO.items():
        con.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES (?, ?)", (chave, valor))
    con.commit()
