<div align="center">

# 📈 Mionions — Crypto Alert Bot

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Binance API](https://img.shields.io/badge/Binance-API-F0B90B?style=for-the-badge&logo=binance&logoColor=black)](https://binance-docs.github.io/apidocs/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)]()

Bot de monitoramento de criptomoedas integrado ao Discord.
Receba alertas instantâneos sempre que um ativo se mover **±5% ou mais** — para cima ou para baixo.

</div>

---

## ✨ Funcionalidades

- **Alertas em tempo real** no Discord com embed rico (preço atual, referência, variação, máxima/mínima 24h, volume)
- **Referência inteligente:** usa o preço de abertura das últimas 24h da Binance como ponto de partida
- **Persistência entre reinicializações:** referências salvas em disco e restauradas automaticamente
- **Slash commands** no Discord: `/precos`, `/status`, `/resetref`
- **Interface gráfica (bot_manager.py):** inicia, para, reinicia e monitora logs sem abrir terminal
- **Bandeja do sistema:** o manager roda minimizado e inicia o bot automaticamente
- **Iniciar com Windows:** opcional via registro do sistema
- **Threshold configurável:** 5%, 10% ou qualquer valor via `.env`
- **Zero custo:** usa a API pública da Binance, sem autenticação necessária

---

## 🖥️ Demonstração

### Alerta de variação

```
⚡ Alerta de Preço — BTC
BTC SUBIU 5.83% desde a referência!

Preço Atual       Preço Ref. (há 2h14m)   Variação
$87,420.00        $82,603.00               🟢 ▲ 5.83%

Máxima 24h        Mínima 24h              Variação 24h
$87,900.00        $81,200.00               🟢 ▲ 6.12%

Volume 24h (USDT): $3,284,500,000
```

---

## 🗂️ Estrutura do Projeto

```
Mionions/
├── Disbot_Mionions.py      # Bot principal — monitoramento e alertas
├── bot_manager.py          # Interface gráfica para gerenciar o bot
├── requirements.txt        # Dependências Python
├── .env                    # Configurações locais (não versionado)
├── .env.example            # Modelo de configuração
├── .gitignore
├── reference_prices.json   # Referências persistidas (gerado automaticamente)
└── README.md
```

---

## ⚙️ Configuração

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/mionions.git
cd mionions
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Criar o arquivo `.env`

```bash
cp .env.example .env
```

Edite o `.env` com suas informações:

| Variável | Descrição | Exemplo |
|---|---|---|
| `DISCORD_TOKEN` | Token do bot (Discord Developer Portal) | `MTQ3...` |
| `CHANNEL_ID` | ID do canal onde os alertas serão enviados | `1440758398068068423` |
| `GUILD_ID` | ID do servidor (para sync instantâneo de slash commands) | `1306313029926916096` |
| `SYMBOLS` | Pares USDT da Binance separados por vírgula | `BTCUSDT,ETHUSDT,SOLUSDT` |
| `ALERT_THRESHOLD` | Variação mínima para alertar (`0.05` = 5%) | `0.05` |
| `CHECK_INTERVAL` | Intervalo de checagem em segundos | `60` |

### 4. Configurar o Bot no Discord

1. Acesse o [Discord Developer Portal](https://discord.com/developers/applications)
2. Crie uma **Application** → **Bot** → copie o Token
3. Em **OAuth2 → URL Generator**: marque `bot` + `applications.commands`
4. Permissões necessárias: `Send Messages`, `Embed Links`
5. Use a URL gerada para convidar o bot ao seu servidor
6. Ative o **Modo Desenvolvedor** no Discord → clique com botão direito no servidor/canal para copiar IDs

---

## 🚀 Uso

### Via Interface Gráfica (recomendado)

```bash
python bot_manager.py
```

O manager inicia minimizado na **bandeja do sistema** e já sobe o bot automaticamente.
Clique no ícone roxo na bandeja para abrir a janela de controle.

### Via Terminal

```bash
python Disbot_Mionions.py
```

---

## 🤖 Slash Commands

| Comando | Descrição |
|---|---|
| `/precos` | Preço atual de todos os ativos monitorados + variação vs referência |
| `/status` | Status do bot: ativos, threshold, intervalo, arquivo de referências |
| `/resetref [ativo]` | Reseta a referência de um ativo específico (ex: `BTC`) ou de `todos` |

> Os comandos aparecem no Discord após o bot iniciar. Se configurou `GUILD_ID`, são sincronizados instantaneamente.

---

## 🧠 Como funciona a referência de preço

```
Bot inicia
    │
    ├─ Arquivo reference_prices.json existe e tem < 24h?
    │       └─ SIM → carrega e continua de onde parou
    │       └─ NÃO → usa openPrice da Binance (preço de 24h atrás)
    │
    └─ A cada CHECK_INTERVAL segundos:
            │
            ├─ variação vs referência >= ALERT_THRESHOLD?
            │       └─ SIM → envia alerta no Discord
            │                 reseta referência para preço atual
            │                 salva em reference_prices.json
            └─ NÃO → aguarda próximo ciclo
```

Isso garante que **qualquer movimento de 5%+, a partir de qualquer ponto no tempo**, seja detectado e notificado — independente de reinicializações.

---

## 📦 Dependências

| Pacote | Uso |
|---|---|
| `discord.py` | Client Discord + slash commands |
| `aiohttp` | Requisições assíncronas à API da Binance |
| `python-dotenv` | Carregamento do `.env` |
| `customtkinter` | Interface gráfica do bot_manager |
| `pystray` | Ícone na bandeja do sistema |
| `Pillow` | Renderização do ícone |
| `psutil` | Gerenciamento de processos |

---

## 🔒 Segurança

- O arquivo `.env` (com token e IDs) está no `.gitignore` e **nunca é versionado**
- A API da Binance utilizada é pública — nenhuma chave de API é necessária
- Nenhum dado de carteira ou conta é acessado

---

## 👤 Autor

**Hugo L. Almeida**

---

<div align="center">
  <sub>Feito com Python + discord.py • API Binance</sub>
</div>
