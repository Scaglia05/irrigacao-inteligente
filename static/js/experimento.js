// Acompanhamento do experimento: lê /api/exp/metricas e permite registrar dados.
(function () {
  const el = (id) => document.getElementById(id);
  const COR_FIXA = { controle_a: "#F0A202", controle_b: "#7C8DB5" };
  let dados = null;
  let chartVolume = null;
  let chartUmidade = null;

  const cssVar = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  const corGrupo = (cod) => COR_FIXA[cod] || cssVar("--secondary");
  const fmt = (v, casas = 1, sufixo = "") =>
    v === null || v === undefined ? "—" : Number(v).toFixed(casas).replace(".", ",") + sufixo;

  function h(tag, props, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else e.setAttribute(k, v);
    }
    for (const f of filhos) if (f !== null && f !== undefined) e.append(f.nodeType ? f : document.createTextNode(f));
    return e;
  }

  // ---------------------------------------------------------------- cards
  function renderCards(grupos) {
    const comEua = grupos.filter((g) => g.eua_g_l !== null);
    const melhor = comEua.length >= 2 ? comEua.reduce((a, b) => (b.eua_g_l > a.eua_g_l ? b : a)).codigo : null;
    const caixa = el("grupoCards");
    caixa.replaceChildren();
    for (const g of grupos) {
      const volume = g.volume_base === "aplicado" ? g.volume_aplicado_l : g.volume_planejado_l;
      const linha = (rotulo, valor) => h("div", null, h("dt", { text: rotulo }), h("dd", { text: valor }));
      const card = h("article", { class: "g-card" + (g.codigo === melhor ? " melhor" : "") },
        h("div", { class: "g-head" },
          h("span", { class: "dot", style: `background:${corGrupo(g.codigo)}` }),
          h("h3", { text: g.nome }),
          h("span", { class: "tag" + (g.codigo === melhor ? " ok" : ""), text: g.codigo === melhor ? "maior EUA" : "volume " + g.volume_base })),
        h("div", { class: "g-eua" },
          h("span", { class: "valor", text: fmt(g.eua_g_l, 1) }),
          h("span", { class: "rotulo", text: "g/L · eficiência do uso da água" })),
        h("dl", { class: "g-metricas" },
          linha("Volume total (L)", fmt(volume, 2)),
          linha("Dias irrigados / decisões", `${g.n_dias_irrigou} / ${g.n_decisoes}`),
          linha("Evitados por previsão de chuva", String(g.acionamentos_evitados_por_chuva)),
          linha("Umidade média do solo", `${fmt(g.umidade.media, 1, "%")} (${g.umidade.n_leituras} leituras)`),
          linha("Massa fresca média (g)", fmt(g.saude.massa_fresca_g_media, 1)),
          linha("Altura média (cm)", fmt(g.saude.altura_cm_media, 1)),
          linha("Folhas (média)", fmt(g.saude.n_folhas_media, 1)),
          linha("Vasos medidos", `${g.saude.n_vasos_medidos} / ${g.n_vasos}`)));
      caixa.append(card);
    }
  }

  // -------------------------------------------------------------- gráficos
  function opcoesBase() {
    const muted = cssVar("--muted");
    const grade = cssVar("--border");
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: muted, boxWidth: 12 } } },
      scales: { x: { ticks: { color: muted, maxTicksLimit: 6 }, grid: { color: grade } }, y: { beginAtZero: true, ticks: { color: muted }, grid: { color: grade } } },
    };
  }

  function renderGraficos(grupos) {
    if (typeof Chart === "undefined") {
      el("notaVolume").textContent = "Gráficos indisponíveis: a biblioteca Chart.js não carregou.";
      el("notaUmidade").textContent = "";
      return;
    }
    if (chartVolume) chartVolume.destroy();
    if (chartUmidade) chartUmidade.destroy();

    const datas = [...new Set(grupos.flatMap((g) => g.serie_volume.map((p) => p.data)))].sort();
    const datasetsVol = grupos.map((g) => {
      const campo = g.volume_base === "aplicado" ? "acum_aplicado_l" : "acum_planejado_l";
      const porData = Object.fromEntries(g.serie_volume.map((p) => [p.data, p[campo]]));
      let ultimo = 0;
      return {
        label: g.nome, borderColor: corGrupo(g.codigo), backgroundColor: corGrupo(g.codigo), tension: 0.15, pointRadius: 3,
        data: datas.map((d) => { if (d in porData) ultimo = porData[d]; return ultimo; }),
      };
    });
    chartVolume = new Chart(el("chartVolume"), { type: "line", data: { labels: datas, datasets: datasetsVol }, options: opcoesBase() });
    el("notaVolume").textContent = datas.length ? "Acumulado por dia; usa o volume aplicado quando há acionamentos registrados, senão o planejado pela decisão." : "Sem decisões registradas ainda.";

    const opU = opcoesBase();
    opU.scales.x = { type: "linear", ticks: { color: cssVar("--muted"), maxTicksLimit: 5, callback: (v) => new Date(v).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) }, grid: { color: cssVar("--border") } };
    opU.scales.y.max = 100;
    const datasetsU = grupos.map((g) => ({
      label: g.nome, borderColor: corGrupo(g.codigo), backgroundColor: corGrupo(g.codigo), tension: 0.2, pointRadius: 2, parsing: false,
      data: g.serie_umidade.map((p) => ({ x: Date.parse(p.ts), y: p.umidade_pct })),
    }));
    chartUmidade = new Chart(el("chartUmidade"), { type: "line", data: { datasets: datasetsU }, options: opU });
    const n = grupos.reduce((s, g) => s + g.umidade.n_leituras, 0);
    el("notaUmidade").textContent = n ? "Últimas 500 leituras por grupo." : "Sem leituras de solo registradas ainda.";
  }

  // -------------------------------------------------------------- previsão
  function renderPrevisao(p) {
    const itens = [
      ["Dias comparados", String(p.n_dias)],
      ["Acurácia", p.acuracia === null ? "—" : fmt(p.acuracia * 100, 0, "%")],
      ["Falsos alarmes", String(p.falsos_alarmes)],
      ["Chuvas não previstas", String(p.chuvas_nao_previstas)],
    ];
    el("prevGrid").replaceChildren(...itens.map(([r, v]) => h("div", { class: "prev-item" }, h("span", { text: r }), h("strong", { text: v }))));
    el("prevNota").textContent = `Previsto = chance de chuva ≥ ${p.limiar_previsao_pct}%; observado = chuva ≥ ${fmt(p.limiar_observado_mm, 1)} mm no dia. ` +
      (p.n_dias ? "" : "Registre decisões e use “Atualizar chuva observada” (a API de histórico leva alguns dias para fechar um dia).");
  }

  // ---------------------------------------------------------------- tabela
  function renderDecisoes(lista, grupos) {
    const nome = Object.fromEntries(grupos.map((g) => [g.codigo, g.nome]));
    const corpo = el("tabelaDecisoes").querySelector("tbody");
    corpo.replaceChildren();
    el("semDecisoes").hidden = lista.length > 0;
    for (const d of lista) {
      const td = (rotulo, texto, classe) => h("td", { "data-rotulo": rotulo, class: classe || "", text: texto });
      corpo.append(h("tr", null,
        td("Data", d.data), td("Grupo", nome[d.grupo] || d.grupo), td("Decisão", d.irrigar ? "Irrigar" : "Não irrigar"),
        td("Volume (L)", fmt(d.volume_l, 2)), td("Motivo", d.motivo, "motivo")));
    }
  }

  // ---------------------------------------------------------------- carga
  function renderTudo() {
    if (!dados) return;
    renderCards(dados.grupos);
    renderGraficos(dados.grupos);
    renderPrevisao(dados.previsao);
    renderDecisoes(dados.decisoes_recentes, dados.grupos);
  }

  async function carregar() {
    try {
      const resp = await fetch("/api/exp/metricas");
      const json = await resp.json();
      if (!json.ok) throw new Error(json.erro || "resposta inválida");
      dados = json;
      renderTudo();
      el("atualizadoEm").textContent = "Atualizado às " + new Date().toLocaleTimeString("pt-BR");
    } catch (err) {
      el("atualizadoEm").textContent = "Falha ao carregar os dados: " + err.message;
    }
  }

  // ---------------------------------------------------------------- escrita
  function msg(texto, tipo) {
    const m = el("statusMsg");
    m.textContent = texto || "";
    m.className = "status-msg" + (tipo ? " " + tipo : "");
  }

  async function enviar(rota, metodo, corpo) {
    const resp = await fetch("/api/exp/" + rota, {
      method: metodo,
      headers: { "Content-Type": "application/json", "X-API-Key": el("token").value },
      body: JSON.stringify(corpo || {}),
    });
    let json = {};
    try { json = await resp.json(); } catch (_) { /* resposta sem JSON */ }
    return { status: resp.status, json };
  }

  async function executar(botao, rotulo, tarefa) {
    botao.disabled = true;
    msg(rotulo + "…", "loading");
    try {
      await tarefa();
    } catch (err) {
      msg("Erro: " + err.message, "error");
    } finally {
      botao.disabled = false;
    }
  }

  function resultadoDecisao(json) {
    const caixa = el("resultadoDecisao");
    caixa.replaceChildren();
    const nome = Object.fromEntries((dados ? dados.grupos : []).map((g) => [g.codigo, g.nome]));
    for (const [cod, r] of Object.entries(json.resultados || {})) {
      caixa.append(h("div", { class: "res-item" }, h("strong", { text: `${nome[cod] || cod}: ` }),
        `${r.irrigar ? "irrigar " + fmt(r.volume_l, 2) + " L (" + fmt(r.duracao_min, 1) + " min)" : "não irrigar"} — ${r.motivo}`));
    }
    for (const [cod, e] of Object.entries(json.erros || {})) {
      caixa.append(h("div", { class: "res-item erro" }, h("strong", { text: `${nome[cod] || cod}: ` }), e));
    }
    caixa.hidden = !caixa.children.length;
  }

  function valores(form) {
    const corpo = {};
    for (const [k, v] of new FormData(form).entries()) if (v !== "") corpo[k] = v;
    return corpo;
  }

  function ligarAcoes() {
    const token = el("token");
    token.value = sessionStorage.getItem("exp-token") || "";
    token.addEventListener("input", () => sessionStorage.setItem("exp-token", token.value));
    el("medData").value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    el("btnAtualizar").addEventListener("click", carregar);

    el("btnDecidir").addEventListener("click", (e) => executar(e.currentTarget, "Decidindo (consulta a previsão do tempo)", async () => {
      const { status, json } = await enviar("decidir", "POST", {});
      resultadoDecisao(json);
      msg(json.ok ? "Decisões do dia registradas." : (json.erro || "Nenhuma decisão registrada."), json.ok && !Object.keys(json.erros || {}).length ? "" : "error");
      if (status === 401 || status === 503) msg(json.erro, "error");
      await carregar();
    }));

    el("btnChuva").addEventListener("click", (e) => executar(e.currentTarget, "Buscando a chuva observada", async () => {
      const { json } = await enviar("chuva-observada/atualizar", "POST", {});
      msg(json.ok ? `Chuva observada atualizada em ${json.atualizados} dia(s).` : json.erro, json.ok ? "" : "error");
      await carregar();
    }));

    el("formLeitura").addEventListener("submit", (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      executar(form.querySelector("button"), "Registrando leitura", async () => {
        const { json } = await enviar("leituras", "POST", { ...valores(form), origem: "manual" });
        msg(json.ok ? "Leitura registrada." : json.erro, json.ok ? "" : "error");
        if (json.ok) { form.umidade_pct.value = ""; await carregar(); }
      });
    });

    el("formMedicao").addEventListener("submit", (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      executar(form.querySelector("button"), "Registrando medição", async () => {
        const { json } = await enviar("medicoes", "POST", valores(form));
        msg(json.ok ? "Medição registrada." : json.erro, json.ok ? "" : "error");
        if (json.ok) await carregar();
      });
    });
  }

  document.addEventListener("themechange", renderTudo);
  ligarAcoes();
  carregar();
})();
