// static/js/app.js
// Logica de interface do painel de irrigacao inteligente.

const el = (id) => document.getElementById(id);

let localAtual = { latitude: -22.3572, longitude: -47.3823, elevation: 630, name: "Araras", admin1: "SP" };
let chartUmidade = null;
let chartConsumo = null;

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function hexToRgba(hex, alpha) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const bigint = parseInt(full, 16);
  const r = (bigint >> 16) & 255, g = (bigint >> 8) & 255, b = bigint & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

function getCores() {
  return {
    primary: cssVar("--primary"),
    secondary: cssVar("--secondary"),
    amber: cssVar("--amber"),
    alert: cssVar("--alert"),
    muted: cssVar("--muted"),
    border: cssVar("--border"),
  };
}

let CORES = getCores();

function initCharts() {
  const ctxU = el("chartUmidade").getContext("2d");
  chartUmidade = new Chart(ctxU, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Umidade do solo (%)",
        data: [],
        borderColor: CORES.primary,
        backgroundColor: hexToRgba(CORES.primary, 0.08),
        pointBackgroundColor: CORES.primary,
        tension: 0.35,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, max: 100, ticks: { color: CORES.muted, callback: (v) => v + "%" }, grid: { color: CORES.border } },
        x: { ticks: { color: CORES.muted }, grid: { color: CORES.border } },
      },
    },
  });

  const ctxC = el("chartConsumo").getContext("2d");
  chartConsumo = new Chart(ctxC, {
    type: "bar",
    data: {
      labels: ["Controle A", "Controle B", "Experimental"],
      datasets: [{
        label: "Volume (L)",
        data: [0, 0, 0],
        backgroundColor: [CORES.amber, CORES.amber, CORES.secondary],
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { color: CORES.muted, callback: (v) => v + "L" }, grid: { color: CORES.border } },
        x: { ticks: { color: CORES.muted }, grid: { color: CORES.border } },
      },
    },
  });
}

function applyChartTheme() {
  CORES = getCores();
  if (chartUmidade) {
    const d = chartUmidade.data.datasets[0];
    d.borderColor = CORES.primary;
    d.backgroundColor = hexToRgba(CORES.primary, 0.08);
    d.pointBackgroundColor = CORES.primary;
    const s = chartUmidade.options.scales;
    s.y.ticks.color = CORES.muted; s.y.grid.color = CORES.border;
    s.x.ticks.color = CORES.muted; s.x.grid.color = CORES.border;
    chartUmidade.update();
  }
  if (chartConsumo) {
    chartConsumo.data.datasets[0].backgroundColor = [CORES.amber, CORES.amber, CORES.secondary];
    const s = chartConsumo.options.scales;
    s.y.ticks.color = CORES.muted; s.y.grid.color = CORES.border;
    s.x.ticks.color = CORES.muted; s.x.grid.color = CORES.border;
    chartConsumo.update();
  }
}
document.addEventListener("themechange", applyChartTheme);

function gerarSerieUmidadeSimulada(umidadeAtual) {
  // Simula os ultimos 7 dias de leitura do sensor, terminando no
  // valor atual configurado pelo usuario (fins de demonstracao —
  // o hardware real ainda nao foi implantado).
  const dias = ["D-6", "D-5", "D-4", "D-3", "D-2", "D-1", "Hoje"];
  const valores = [];
  let v = umidadeAtual + (Math.random() * 20 - 10);
  for (let i = 0; i < 6; i++) {
    v += (Math.random() * 14 - 7);
    v = Math.max(15, Math.min(85, v));
    valores.push(Math.round(v));
  }
  valores.push(Math.round(umidadeAtual));
  return { dias, valores };
}

function atualizarMockStats(clima, resultado) {
  el("mockUmidade").textContent = `${el("umidadeSolo").value}%`;

  const horasChuva = clima.precipitation_prob_24h >= 60 ? "em breve" : `${clima.precipitation_prob_24h.toFixed(0)}% em 24h`;
  el("mockChuva").textContent = horasChuva;

  const statusEl = el("mockStatus");
  if (resultado.irrigar) {
    statusEl.textContent = "Irrigando";
    statusEl.className = "mock-stat-value irrigando";
  } else {
    statusEl.textContent = "Aguardando";
    statusEl.className = "mock-stat-value aguardando";
  }

  const { dias, valores } = gerarSerieUmidadeSimulada(parseFloat(el("umidadeSolo").value));
  chartUmidade.data.labels = dias;
  chartUmidade.data.datasets[0].data = valores;
  chartUmidade.update();
}

function atualizarMockComparacao(resultados) {
  chartConsumo.data.datasets[0].data = [
    resultados.controle_a.volume_l,
    resultados.controle_b.volume_l,
    resultados.experimental.volume_l,
  ];
  chartConsumo.update();
}

const GRUPO_DESC = {
  controle_a: "Aciona a irrigação sempre no mesmo horário, com lâmina fixa — não considera clima nem umidade do solo.",
  controle_b: "Reage apenas à umidade do solo. Ignora a previsão do tempo.",
  experimental: "Combina umidade do solo, cálculo de ETc (Penman-Monteith / FAO-56) e previsão climática.",
};

function atualizarCamposPorGrupo() {
  const grupo = el("grupo").value;
  el("grupoDesc").textContent = GRUPO_DESC[grupo];

  el("camposUmidade").style.display = grupo === "controle_a" ? "none" : "flex";
  el("camposEtc").style.display = grupo === "experimental" ? "block" : "none";
  el("campoLaminaFixa").style.display = grupo === "experimental" ? "none" : "block";
}

async function buscarLocal() {
  const cidade = el("cidade").value.trim();
  if (!cidade) return;
  el("localInfo").textContent = "Buscando...";
  try {
    const resp = await fetch(`/api/localizacao?cidade=${encodeURIComponent(cidade)}`);
    const data = await resp.json();
    if (!data.ok) throw new Error(data.erro);
    localAtual = data.local;
    el("localInfo").textContent =
      `${data.local.name}${data.local.admin1 ? " - " + data.local.admin1 : ""}, ${data.local.country} (${data.local.latitude.toFixed(2)}, ${data.local.longitude.toFixed(2)})`;
  } catch (err) {
    el("localInfo").textContent = `Não encontrado: ${err.message}`;
  }
}

function payloadBase() {
  return {
    latitude: localAtual.latitude,
    longitude: localAtual.longitude,
    elevation: localAtual.elevation,
    area_m2: parseFloat(el("areaM2").value) || 0.25,
    vazao_l_h: parseFloat(el("vazaoLH").value) || 120,
    umidade_solo: parseFloat(el("umidadeSolo").value),
    fase_cultura: el("faseCultura").value,
    lamina_fixa_mm: parseFloat(el("laminaFixa").value) || 3.5,
  };
}

function setStatus(msg, cls) {
  const s = el("statusMsg");
  s.textContent = msg || "";
  s.className = "status-msg" + (cls ? " " + cls : "");
}

function formatWeatherStrip(clima) {
  const chips = [
    `🌡️ <b>${clima.t_min.toFixed(1)}° – ${clima.t_max.toFixed(1)}°C</b>`,
    `💧 Umidade do ar <b>${clima.rh_mean.toFixed(0)}%</b>`,
    `🌬️ Vento <b>${(clima.wind_speed_10m * 3.6).toFixed(1)} km/h</b>`,
    `☀️ Radiação <b>${clima.solar_radiation.toFixed(1)} MJ/m²</b>`,
    `🌧️ Chance de chuva (24h) <b>${clima.precipitation_prob_24h.toFixed(0)}%</b>`,
  ];
  return chips.map((c) => `<span class="weather-chip">${c}</span>`).join("");
}

function renderResultado(clima, resultado) {
  el("resultEmpty").style.display = "none";
  el("resultContent").style.display = "block";

  const banner = el("decisionBanner");
  banner.className = "decision-banner " + (resultado.irrigar ? "irrigar" : "nao-irrigar");
  el("decisionIcon").textContent = resultado.irrigar ? "💧" : "⏸️";
  el("decisionTitle").textContent = resultado.irrigar
    ? `Irrigação ACIONADA — ${resultado.grupo}`
    : `Irrigação NÃO acionada — ${resultado.grupo}`;
  el("decisionReason").textContent = resultado.motivo;

  el("metricVolume").textContent = `${resultado.volume_l.toFixed(2)} L`;
  el("metricDuracao").textContent = `${resultado.duracao_min.toFixed(1)} min`;

  const usaEtc = !!resultado.usa_etc;
  el("cardEto").style.display = usaEtc ? "flex" : "none";
  el("cardEtc").style.display = usaEtc ? "flex" : "none";
  if (usaEtc) {
    el("metricEto").textContent = `${resultado.eto_mm_dia.toFixed(2)} mm/dia`;
    el("metricEtc").textContent = `${resultado.etc_mm_dia.toFixed(2)} mm/dia`;
  }

  el("formulaStrip").style.display = usaEtc ? "flex" : "none";
  if (usaEtc) {
    el("formulaDetail").textContent =
      `${resultado.etc_mm_dia.toFixed(2)} = ${resultado.eto_mm_dia.toFixed(2)} × ${resultado.kc.toFixed(2)}  ·  Volume = ETc × área (${resultado.volume_l.toFixed(2)} L)`;
  }

  el("weatherStrip").innerHTML = formatWeatherStrip(clima);
}

async function calcular() {
  const btn = el("btnCalcular");
  btn.disabled = true;
  setStatus("Consultando previsão do tempo e calculando...", "loading");
  el("comparisonPanel").style.display = "none";

  try {
    const payload = { ...payloadBase(), grupo: el("grupo").value };
    const resp = await fetch("/api/calcular", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.erro);
    renderResultado(data.clima, data.resultado);
    atualizarMockStats(data.clima, data.resultado);
    setStatus("Cálculo concluído.", "");
  } catch (err) {
    setStatus(`Erro: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
  }
}

function compareCardHtml(key, r) {
  const destaque = key === "experimental" ? "destaque" : "";
  const badge = r.irrigar
    ? '<span class="badge on">Irrigando</span>'
    : '<span class="badge off">Aguardando</span>';
  let extra = "";
  if (r.usa_etc) {
    extra = `<div class="compare-metric"><span>ETc</span><span>${r.etc_mm_dia.toFixed(2)} mm/dia</span></div>`;
  }
  return `
    <div class="compare-card ${destaque}">
      <h3>${r.grupo}</h3>
      <div class="estrategia">${r.estrategia}</div>
      ${badge}
      <div class="compare-metric"><span>Volume</span><span>${r.volume_l.toFixed(2)} L</span></div>
      <div class="compare-metric"><span>Duração</span><span>${r.duracao_min.toFixed(1)} min</span></div>
      ${extra}
      <div class="compare-reason">${r.motivo}</div>
    </div>`;
}

async function comparar() {
  const btn = el("btnComparar");
  btn.disabled = true;
  setStatus("Calculando os três grupos...", "loading");

  try {
    const payload = payloadBase();
    const resp = await fetch("/api/comparar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.erro);

    const grid = el("comparisonGrid");
    grid.innerHTML =
      compareCardHtml("controle_a", data.resultados.controle_a) +
      compareCardHtml("controle_b", data.resultados.controle_b) +
      compareCardHtml("experimental", data.resultados.experimental);
    el("comparisonPanel").style.display = "block";
    atualizarMockComparacao(data.resultados);
    setStatus("Comparativo atualizado.", "");
  } catch (err) {
    setStatus(`Erro: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
  }
}

// ---------- Event listeners ----------
el("grupo").addEventListener("change", atualizarCamposPorGrupo);
el("umidadeSolo").addEventListener("input", () => {
  el("umidadeSoloValor").textContent = `${el("umidadeSolo").value}%`;
});
el("btnBuscarLocal").addEventListener("click", buscarLocal);
el("btnCalcular").addEventListener("click", calcular);
el("btnComparar").addEventListener("click", comparar);

// Inicialização
initCharts();
atualizarCamposPorGrupo();
buscarLocal();
