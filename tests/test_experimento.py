"""
Testes do acompanhamento do experimento (API, regras de negocio e paginas).

Rodar na raiz do projeto:  python -m unittest discover -s tests -v
Nao exigem internet: a previsao do tempo e a chuva observada sao simuladas.
"""

import copy
import os
import tempfile
import unittest
from datetime import date
from unittest import mock

from app import app
from experimento import servico
from experimento.db import conectar

TOKEN = "token-de-teste"
CLIMA = {
    "date": "2026-11-10", "t_max": 25.4, "t_min": 13.8, "rh_mean": 71, "wind_speed_10m": 3.0,
    "solar_radiation": 22.82, "precipitation": 0.0, "precipitation_prob_24h": 35.0,
    "elevation": 617, "latitude": -22.4114, "day_of_year": 314,
}
AUTH = {"X-API-Key": TOKEN}


def clima(data="2026-11-10", prob=35.0):
    c = copy.deepcopy(CLIMA)
    c["date"], c["precipitation_prob_24h"] = data, prob
    return c


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.caminho = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.env = mock.patch.dict(os.environ, {"INGEST_TOKEN": TOKEN})
        self.env.start()
        app.config.update(TESTING=True, DATABASE_PATH=self.caminho, BUSCAR_CLIMA=lambda *a: clima())
        self.c = app.test_client()

    def tearDown(self):
        self.env.stop()
        app.config.pop("DATABASE_PATH", None)
        app.config.pop("BUSCAR_CLIMA", None)
        app.config.pop("BUSCAR_CHUVA", None)
        os.remove(self.caminho)

    def post(self, rota, corpo, headers=AUTH):
        return self.c.post(f"/api/exp/{rota}", json=corpo, headers=headers)

    def metricas(self):
        return self.c.get("/api/exp/metricas").get_json()

    def grupo(self, codigo):
        return next(g for g in self.metricas()["grupos"] if g["codigo"] == codigo)


class TestAutenticacao(Base):
    def test_sem_token_configurado_a_escrita_fica_desativada(self):
        with mock.patch.dict(os.environ, {"INGEST_TOKEN": ""}):
            r = self.post("leituras", {"grupo": "controle_b", "umidade_pct": 40})
        self.assertEqual(r.status_code, 503)

    def test_token_errado_ou_ausente(self):
        corpo = {"grupo": "controle_b", "umidade_pct": 40}
        self.assertEqual(self.post("leituras", corpo, headers={}).status_code, 401)
        self.assertEqual(self.post("leituras", corpo, headers={"X-API-Key": "errado"}).status_code, 401)

    def test_token_correto_grava(self):
        self.assertEqual(self.post("leituras", {"grupo": "controle_b", "umidade_pct": 40}).status_code, 201)

    def test_leitura_das_metricas_e_publica(self):
        self.assertEqual(self.c.get("/api/exp/metricas").status_code, 200)


class TestValidacao(Base):
    def test_leitura_invalida(self):
        for corpo in ({"grupo": "controle_b", "umidade_pct": 150}, {"grupo": "controle_b", "umidade_pct": "abc"},
                      {"grupo": "controle_b"}, {"grupo": "inexistente", "umidade_pct": 40},
                      {"grupo": "controle_b", "umidade_pct": 40, "ts": "ontem"}):
            with self.subTest(corpo=corpo):
                r = self.post("leituras", corpo)
                self.assertEqual(r.status_code, 400)
                self.assertFalse(r.get_json()["ok"])

    def test_corpo_nao_json(self):
        r = self.c.post("/api/exp/leituras", data="texto", headers=AUTH)
        self.assertEqual(r.status_code, 400)

    def test_medicao_invalida(self):
        base = {"grupo": "experimental", "data": "2026-11-20", "massa_fresca_g": 30}
        for extra in ({"vaso": 4}, {"vaso": 0}, {"vaso": 1.5}, {"vaso": 1, "massa_fresca_g": -1},
                      {"vaso": 1, "data": "20/11/2026"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.post("medicoes", {**base, **extra}).status_code, 400)
        self.assertEqual(self.post("medicoes", {"grupo": "experimental", "vaso": 1, "data": "2026-11-20"}).status_code, 400)

    def test_acionamento_negativo(self):
        self.assertEqual(self.post("acionamentos", {"grupo": "experimental", "volume_l": -2}).status_code, 400)

    def test_configuracao(self):
        for corpo in ({"lamina_fixa_mm": -1}, {"fase_cultura": "x"}, {"desconhecido": 1}, {}):
            with self.subTest(corpo=corpo):
                r = self.c.put("/api/exp/config", json=corpo, headers=AUTH)
                self.assertEqual(r.status_code, 400)
        r = self.c.put("/api/exp/config", json={"lamina_fixa_mm": 4.5, "fase_cultura": "final"}, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["config"]["lamina_fixa_mm"], 4.5)

    def test_csv_tabela_desconhecida(self):
        self.assertEqual(self.c.get("/api/exp/export/usuarios.csv").status_code, 400)


class TestDecisao(Base):
    def test_sem_leitura_so_o_controle_a_decide(self):
        r = self.post("decidir", {})
        j = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(j["resultados"]), ["controle_a"])
        self.assertEqual(set(j["erros"]), {"controle_b", "experimental"})

    def test_tres_grupos_com_leitura(self):
        self.post("leituras", {"grupo": "controle_b", "umidade_pct": 40})
        self.post("leituras", {"grupo": "experimental", "umidade_pct": 40})
        j = self.post("decidir", {}).get_json()
        self.assertEqual(set(j["resultados"]), {"controle_a", "controle_b", "experimental"})
        a, b, e = (j["resultados"][k] for k in ("controle_a", "controle_b", "experimental"))
        self.assertEqual(a["volume_l"], 0.94)  # 3,75 mm x 0,25 m2
        self.assertFalse(b["irrigar"])  # 40% acima do limiar de 35%
        self.assertEqual(e["codigo"], "etc")
        self.assertAlmostEqual(e["volume_l"], round(e["etc_mm_dia"] * 0.25, 2), places=2)

    def test_umidade_enviada_no_corpo_tem_prioridade(self):
        self.post("leituras", {"grupo": "controle_b", "umidade_pct": 60})
        j = self.post("decidir", {"grupo": "controle_b", "umidade": {"controle_b": 20}}).get_json()
        self.assertTrue(j["resultados"]["controle_b"]["irrigar"])

    def test_uma_decisao_por_grupo_e_dia(self):
        self.post("leituras", {"grupo": "experimental", "umidade_pct": 40})
        self.post("decidir", {"grupo": "experimental"})
        self.post("decidir", {"grupo": "experimental"})
        self.assertEqual(self.grupo("experimental")["n_decisoes"], 1)

    def test_chuva_prevista_cancela_e_conta_como_evitado(self):
        app.config["BUSCAR_CLIMA"] = lambda *a: clima(prob=80)
        self.post("leituras", {"grupo": "experimental", "umidade_pct": 40})
        j = self.post("decidir", {"grupo": "experimental"}).get_json()
        self.assertEqual(j["resultados"]["experimental"]["codigo"], "chuva_prevista")
        g = self.grupo("experimental")
        self.assertEqual(g["acionamentos_evitados_por_chuva"], 1)
        self.assertEqual(g["volume_planejado_l"], 0)

    def test_falha_na_previsao_retorna_502(self):
        def falha(*_):
            raise RuntimeError("sem rede")
        app.config["BUSCAR_CLIMA"] = falha
        self.assertEqual(self.post("decidir", {}).status_code, 502)

    def test_config_altera_a_decisao(self):
        self.c.put("/api/exp/config", json={"lamina_fixa_mm": 5.0}, headers=AUTH)
        j = self.post("decidir", {"grupo": "controle_a"}).get_json()
        self.assertEqual(j["resultados"]["controle_a"]["volume_l"], 1.25)


class TestMetricas(Base):
    def test_banco_vazio_nao_quebra(self):
        m = self.metricas()
        self.assertTrue(m["ok"])
        self.assertEqual([g["codigo"] for g in m["grupos"]], ["controle_a", "controle_b", "experimental"])
        for g in m["grupos"]:
            self.assertIsNone(g["eua_g_l"])
            self.assertEqual(g["volume_planejado_l"], 0)
            self.assertEqual(g["serie_volume"], [])
        self.assertIsNone(m["previsao"]["acuracia"])

    def test_volume_aplicado_substitui_o_planejado(self):
        self.post("decidir", {"grupo": "controle_a"})
        self.assertEqual(self.grupo("controle_a")["volume_base"], "planejado")
        self.post("acionamentos", {"grupo": "controle_a", "volume_l": 0.8, "duracao_min": 0.4, "ts": "2026-11-10T09:00:00Z"})
        g = self.grupo("controle_a")
        self.assertEqual(g["volume_base"], "aplicado")
        self.assertEqual(g["volume_aplicado_l"], 0.8)
        self.assertEqual(g["serie_volume"][0]["acum_aplicado_l"], 0.8)

    def test_eua_por_vaso(self):
        self.post("acionamentos", {"grupo": "experimental", "volume_l": 3.0})
        for vaso, massa in ((1, 30), (2, 32), (3, 34)):
            self.assertEqual(self.post("medicoes", {"grupo": "experimental", "vaso": vaso, "data": "2026-12-05",
                                                    "altura_cm": 12, "n_folhas": 5, "massa_fresca_g": massa}).status_code, 201)
        g = self.grupo("experimental")
        # 3 L no grupo = 1 L por vaso; massa fresca media 32 g -> 32 g/L
        self.assertAlmostEqual(g["eua_g_l"], 32.0)
        self.assertEqual(g["saude"]["n_vasos_medidos"], 3)
        self.assertAlmostEqual(g["saude"]["altura_cm_media"], 12.0)

    def test_medicao_mais_recente_vale_e_campos_vazios_preservam(self):
        self.post("medicoes", {"grupo": "controle_a", "vaso": 1, "data": "2026-12-01", "massa_fresca_g": 10, "altura_cm": 8})
        self.post("medicoes", {"grupo": "controle_a", "vaso": 1, "data": "2026-12-01", "n_folhas": 4})
        self.post("medicoes", {"grupo": "controle_a", "vaso": 1, "data": "2026-12-08", "massa_fresca_g": 20})
        s = self.grupo("controle_a")["saude"]
        self.assertEqual(s["massa_fresca_g_media"], 20)
        self.assertEqual(s["n_vasos_medidos"], 1)
        csv = self.c.get("/api/exp/export/medicoes.csv").get_data(as_text=True).splitlines()
        self.assertIn("2026-12-01", csv[1])
        self.assertIn(",4,", csv[1])  # n_folhas preservado pelo upsert parcial

    def test_precisao_da_previsao(self):
        con = conectar(self.caminho)
        try:
            for data, prob in (("2026-11-01", 80), ("2026-11-02", 10), ("2026-11-03", 70), ("2026-11-04", 5), ("2026-11-20", 90)):
                servico.decidir(con, "controle_a", clima(data, prob))
            chuva = {"2026-11-01": 5.0, "2026-11-02": 0.0, "2026-11-03": 0.0, "2026-11-04": 3.0}
            n = servico.atualizar_chuva_observada(con, lambda *a: chuva, hoje=date(2026, 11, 10))
        finally:
            con.close()
        self.assertEqual(n, 4)  # 20/11 e futuro e fica de fora
        p = self.metricas()["previsao"]
        self.assertEqual((p["n_dias"], p["acertos"], p["falsos_alarmes"], p["chuvas_nao_previstas"]), (4, 2, 1, 1))
        self.assertAlmostEqual(p["acuracia"], 0.5)

    def test_atualizar_chuva_via_api_com_falha(self):
        def falha(*_):
            raise RuntimeError("sem rede")
        app.config["BUSCAR_CHUVA"] = falha
        con = conectar(self.caminho)
        try:
            servico.decidir(con, "controle_a", clima("2020-01-01", 50))
        finally:
            con.close()
        self.assertEqual(self.post("chuva-observada/atualizar", {}).status_code, 502)

    def test_serie_de_umidade_ordenada(self):
        for ts, u in (("2026-11-10T10:15:00Z", 41), ("2026-11-10T10:00:00Z", 40), ("2026-11-10T10:30:00Z", 39)):
            self.post("leituras", {"grupo": "controle_b", "umidade_pct": u, "ts": ts})
        serie = self.grupo("controle_b")["serie_umidade"]
        self.assertEqual([p["umidade_pct"] for p in serie], [40, 41, 39])

    def test_exportacao_csv(self):
        self.post("leituras", {"grupo": "controle_b", "umidade_pct": 33.5, "ts": "2026-11-10T10:00:00Z"})
        r = self.c.get("/api/exp/export/leituras.csv")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.mimetype.startswith("text/csv"))
        linhas = r.get_data(as_text=True).splitlines()
        self.assertEqual(linhas[0], "id,grupo,ts,umidade_pct,origem")
        self.assertIn("controle_b,2026-11-10T10:00:00+00:00,33.5,sensor", linhas[1])


class TestPaginas(Base):
    def test_paginas_respondem_e_se_ligam(self):
        for rota in ("/", "/apresentacao", "/experimento"):
            with self.subTest(rota=rota):
                r = self.c.get(rota)
                self.assertEqual(r.status_code, 200)
                html = r.get_data(as_text=True)
                self.assertIn('href="/experimento"', html)
                self.assertIn('id="themeToggle"', html)

    def test_comparar_usa_lamina_em_mm(self):
        with mock.patch("irrigation.weather.fetch_today_weather", return_value=clima()):
            j = self.c.post("/api/comparar", json={"area_m2": 1.0, "umidade_solo": 20}).get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["resultados"]["controle_a"]["volume_l"], 3.75)
        self.assertEqual(j["resultados"]["controle_b"]["volume_l"], 3.75)


if __name__ == "__main__":
    unittest.main()
