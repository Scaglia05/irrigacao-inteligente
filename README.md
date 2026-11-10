# Sistema de Irrigação Inteligente — Protótipo Web (TCC)

Protótipo funcional do sistema de irrigação inteligente descrito no
projeto de pesquisa: um painel web que calcula a necessidade hídrica
de uma cultura em tempo real (evapotranspiração pelo método
Penman-Monteith / FAO-56), consulta a previsão climática, e decide
se e quanto irrigar — comparando essa decisão com os dois métodos
tradicionais (tempo fixo e limiar simples de umidade) usados como
grupos controle no experimento.

> Este protótipo demonstra a **lógica de decisão** do sistema (a
> parte que, no TCC final, roda no backend em C#/.NET). Aqui ela foi
> implementada em Python/Flask para facilitar a hospedagem gratuita
> no Render sem precisar de infraestrutura adicional — o cálculo
> matemático (Penman-Monteith FAO-56) é idêntico em ambos os casos.

## O que o painel faz

- **Dropdown "Aspersor / Grupo experimental"** — escolha entre os 3
  grupos do experimento:
  - **Controle A** — irrigação programada, com lâmina fixa por acionamento (sempre a mesma duração)
  - **Controle B** — irrigação por limiar simples de umidade do solo
  - **Experimental** — sistema completo: umidade do solo + ETc + previsão climática
- **Cálculo real de ETo** pelo método Penman-Monteith (FAO-56), usando
  dados climáticos reais da localização escolhida (Open-Meteo).
- **Cálculo de ETc = ETo × Kc**, com os coeficientes de cultura do
  rabanete usados no TCC (inicial 0,70 / médio 0,90 / final 0,85).
- **Conversão para volume (L) e tempo de irrigação (min)**, a partir
  da área da cultura e da vazão do aspersor.
- **Cancelamento automático da irrigação** quando há previsão de
  chuva relevante nas próximas 24h (apenas no grupo Experimental).
- **Botão "Comparar os 3 grupos"** — mostra lado a lado o que cada
  estratégia decidiria fazer, no mesmo dia — ótimo para a apresentação.

## Como rodar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Acesse **http://localhost:5000**.

## Como publicar no Render

1. Crie um repositório no GitHub e suba esta pasta inteira para lá
   (`git init`, `git add .`, `git commit -m "primeira versão"`,
   `git push`).
2. Em [render.com](https://render.com), clique em **New +** →
   **Web Service**.
3. Conecte o repositório do GitHub.
4. O Render deve detectar automaticamente o arquivo `render.yaml`
   e preencher tudo sozinho. Se pedir manualmente:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Plan:** Free
5. Clique em **Create Web Service** e aguarde o build (leva 1–2 min).
6. Pronto — o Render vai gerar uma URL pública tipo
   `https://irrigacao-inteligente.onrender.com`.

Não é necessário configurar nenhuma variável de ambiente nem chave de
API: a previsão do tempo é obtida via **Open-Meteo**, que é gratuita
e não exige cadastro.

> **Nota sobre o plano gratuito do Render:** no plano free, o serviço
> "dorme" após alguns minutos sem uso e demora ~30s para acordar na
> primeira requisição seguinte. Isso é normal — se for apresentar ao
> vivo, acesse o link uns minutos antes para "acordar" o serviço.

## Estrutura do projeto

```
irrigacao-app/
├── app.py                  # Servidor Flask e rotas da API
├── irrigation/
│   ├── eto.py               # Cálculo de ETo (Penman-Monteith FAO-56)
│   ├── weather.py            # Integração com Open-Meteo
│   └── decision.py           # Lógica de decisão dos 3 grupos
├── templates/
│   └── index.html           # Painel (dashboard)
├── static/
│   ├── css/style.css        # Estilo visual
│   └── js/app.js             # Interatividade do painel
├── requirements.txt
├── render.yaml               # Configuração de deploy do Render
└── README.md
```

## Referências científicas usadas no cálculo

- ALLEN, R. G.; PEREIRA, L. S.; RAES, D.; SMITH, M. *Crop
  evapotranspiration: guidelines for computing crop water
  requirements.* FAO Irrigation and Drainage Paper 56. Rome: FAO, 1998.
- ZOTARELLI, L. et al. *Step by step calculation of the
  Penman-Monteith evapotranspiration (FAO-56 method).* AE459.
  University of Florida, IFAS Extension, 2010.
- Dados climáticos: [Open-Meteo](https://open-meteo.com) (API
  gratuita, sem necessidade de chave de acesso).

---
Projeto de TCC — Engenharia de Computação, Fundação Hermínio Ometto (FHO).
Autor: Guilherme Augusto Scaglia · Orientador: Prof. Pedro Luís Antonelli.
