# Football Predictor AI ⚽🏈🏀🥊📊
### Inteligência Preditiva Esportiva, Engenharia de Dados & Value Betting

Uma plataforma completa de análise estatística e modelagem preditiva para múltiplas modalidades esportivas (**Futebol, NFL, Basquete, MMA/UFC, Beisebol, Hóquei, Handebol, Rugby, Vôlei, AFL e eSports**), integrando **FastAPI**, **Distribuição de Poisson**, **Médias Ponderadas Móveis com isolamento estrito de mando de campo (Casa vs Fora)**, integração com a suíte oficial **API-Sports (11 modalidades)**, **OddsPapi**, **SharpAPI**, **PandaScore**, **Gemini AI** e um **Dashboard Web Reativo de Alta Performance**.

---

## 🚀 Principais Recursos

1. **Suíte Multi-Esportes Integrada (API-Sports Oficial):**
   - **11 modalidades esportivas** configuradas com autenticação isolada e cache em memória:
     - Futebol (`https://v3.football.api-sports.io`)
     - Basquete (`https://v1.basketball.api-sports.io`) & NBA (`https://v2.nba.api-sports.io`)
     - MMA / UFC (`https://v1.mma.api-sports.io`)
     - Beisebol / MLB (`https://v1.baseball.api-sports.io`)
     - Hóquei no Gelo / NHL (`https://v1.hockey.api-sports.io`)
     - Vôlei (`https://v1.volleyball.api-sports.io`)
     - Handebol (`https://v1.handball.api-sports.io`)
     - Rugby (`https://v1.rugby.api-sports.io`)
     - AFL / Futebol Australiano (`https://v1.afl.api-sports.io`)
     - Futebol Americano / NFL (`https://v1.american-football.api-sports.io`)
   - Normalização polimórfica de eventos para formato canônico universal.
   - Enriquecimento tático e cotações em tempo real via **OddsPapi** e **SharpAPI**.
   - Cobertura de eSports via **PandaScore** (CS2, LoL, Valorant, Dota 2).
   - Timeouts estritos e tolerância zero a dados sintéticos descontrolados.

2. **Sistema de Cache em Memória Inteligente:**
   - Cache assíncrono e thread-safe com TTL diferenciado para preservar as cotas:
     - **5 minutos** para partidas e eventos esportivos.
     - **10 minutos** para cotações e odds de mercado.
     - **4 horas** para históricos e estatísticas consolidadas.

3. **Motor Preditivo & Estatístico Sênior (`engine.py`):**
   - **Distribuição Bivariada de Poisson:** Probabilidades de gols exatos ($0$ a $5+$), gerando matriz de placares prováveis e probabilidades precisas para *Over 1.5*, *Over 2.5*, *Under 2.5*, *Ambas Marcam (BTTS)* e *1X2*.
   - **Médias Ponderadas Móveis:** Ponderação linear decrescente priorizando desempenhos recentes.
   - **Isolamento de Mando de Campo:** Desempenho mandante em casa contra defesa visitante fora.
   - **Análise de Escanteios, Finalizações e Laterais.**
   - **Score de Confiança Transparente:** Classificação em **Alta Confiança (≥ 75%)** e **Moderada (60% a 74%)**.

4. **Dashboard Web Reativo:**
   - Interface moderna em Dark Glassmorphism com Tailwind CSS.
   - Indicadores numéricos no topo, filtros instantâneos por mercado e modal de Raio-X com heatmap de Poisson.

---

## 📁 Estrutura do Projeto

```
c:\Users\dPaD\Desktop\PROJETOS\APOSTAS\
├── .env.example              # Modelo de variáveis de ambiente
├── .env                      # Arquivo de configuração ativo
├── requirements.txt          # Dependências do Python (FastAPI, Uvicorn, HTTPX, etc.)
├── config.py                 # Configurações de ambiente, timeouts e chaves de API
├── cache.py                  # Cache assíncrono em memória com TTL
├── apisports_service.py      # Cliente HTTP multi-esporte unificado (12 modalidades API-Sports)
├── odds_service.py           # Cliente HTTP e de cotações para a OddsPapi
├── american_football_service.py # Integração oficial API-Sports American Football (NFL)
├── nfl_service.py            # Integração Big Balls Data NFL
├── sharpapi_service.py       # Integração SharpAPI (DraftKings, FanDuel)
├── pandascore_service.py     # Integração PandaScore (eSports)
├── gemini_analyzer.py        # Análise tática preditiva com IA Gemini
├── engine.py                 # Motor estatístico (Poisson, Médias Ponderadas, Confiança)
├── football_orchestrator.py  # Orquestrador de dados e predições
├── football_games_service.py # Serviço de partidas com tolerância zero a mocks
├── main.py                   # Servidor FastAPI com rotas de API e arquivos estáticos
├── README.md                 # Documentação completa
└── static/
    ├── index.html            # Estrutura do painel web
    ├── style.css             # Estilos customizados, glassmorphism e heatmap de Poisson
    └── app.js                # Lógica reativa, filtros instantâneos e modal de Raio-X
```

---

## 🛠️ Guia Rápido de Instalação e Execução

### 1. Pré-requisitos
- Python 3.10 ou superior instalado.

### 2. Instalar as dependências
Abra o terminal na pasta do projeto e execute:
```bash
pip install -r requirements.txt
```

### 3. Configurar as Chaves de API no .env
Edite o arquivo `.env` e configure suas chaves de API conforme `.env.example`.

### 4. Iniciar o Servidor
Execute o comando abaixo:
```bash
python -m uvicorn main:app --reload --port 8000
```

### 5. Acessar o Dashboard
Abra seu navegador no endereço:
```
http://127.0.0.1:8000
```

---

## 📡 Endpoints da API

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/` | Retorna o dashboard web reativo (`index.html`) |
| `GET` | `/api/status` | Exibe o status consolidado do sistema e catálogo de esportes |
| `GET` | `/api/sports/status` | Status detalhado e cotas das 12 modalidades da API-Sports |
| `GET` | `/api/sports/{sport}/status` | Status, conta e limites de uma modalidade específica |
| `GET` | `/api/sports/{sport}/jogos` | Grade de jogos/eventos normalizados da modalidade (`?data=YYYY-MM-DD`) |
| `GET` | `/api/sports/{sport}/ao-vivo` | Eventos ao vivo (in-play) da modalidade |
| `POST` | `/api/config/apisports-key` | Atualiza a chave de API da API-Sports para uma modalidade ou globalmente |
| `GET` | `/api/partidas-analisadas` | Retorna partidas de futebol do dia processadas pelo motor preditivo |
| `GET` | `/api/partida/{fixture_id}/raio-x` | Retorna scouts aprofundados e matriz de placares da partida |
| `GET` | `/api/top5-bets` | Retorna as Top 5 Bets consolidadas de Futebol e NFL |

---

## 🧠 Fórmulas & Metodologia Estatística

### 1. Distribuição de Poisson
Para modelar o número de gols $k$ marcados por uma equipe com expectativa $\lambda$:
$$P(X = k) = \frac{e^{-\lambda} \cdot \lambda^k}{k!}$$

As probabilidades combinadas de placar $(i, j)$ assumem independência bivariada:
$$P(\text{Casa} = i, \text{Fora} = j) = P(\text{Casa} = i) \times P(\text{Fora} = j)$$

A partir da matriz de placares, o sistema calcula de forma exata:
- **Over 1.5:** $1 - (P(0,0) + P(1,0) + P(0,1))$
- **Over 2.5:** $1 - \sum_{i+j \le 2} P(i,j)$
- **Ambas Marcam (Sim):** $(1 - P(\text{Casa}=0)) \times (1 - P(\text{Fora}=0))$

### 2. Média Ponderada Móvel
Para os últimos $n$ jogos da equipe, o jogo mais recente recebe peso $n$, enquanto o mais antigo recebe peso $1$:
$$\bar{x}_{\text{ponderada}} = \frac{\sum_{i=1}^{n} w_i \cdot x_i}{\sum_{i=1}^{n} w_i}$$

---

## 🛡️ Licença e Uso
Desenvolvido para análise esportiva profissional, estudos probabilísticos e automação analítica.
