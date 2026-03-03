import sys
import os
import json
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# Força UTF-8 no terminal (necessário no Windows com cp1252)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

# ─── Configurações ───────────────────────────────────────────────────────────

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
GUILD_ID = int(os.getenv("GUILD_ID") or 0)

ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.05"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))

SYMBOLS = [s.strip().upper() for s in os.getenv(
    "SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,UNIUSDT,LDOUSDT,DOTUSDT"
).split(",")]

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"

# Arquivo de persistência das referências
REFERENCE_FILE = "reference_prices.json"

# Se a referência salva tiver mais de X horas, descarta e usa o openPrice da Binance
REFERENCE_MAX_AGE_HOURS = 24

# ─── Estado interno ──────────────────────────────────────────────────────────

reference_prices: dict[str, float] = {}
reference_timestamps: dict[str, datetime] = {}  # quando cada referência foi definida
current_prices: dict[str, float] = {}
last_tickers: dict[str, dict] = {}

# ─── Persistência ────────────────────────────────────────────────────────────

def save_references():
    """Salva referências em disco para sobreviver a reinicializações."""
    data = {
        sym: {
            "price": price,
            "saved_at": reference_timestamps.get(sym, datetime.now(timezone.utc)).isoformat(),
        }
        for sym, price in reference_prices.items()
    }
    try:
        with open(REFERENCE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WARN] Não foi possível salvar referências: {e}")


def load_references() -> dict[str, tuple[float, datetime]]:
    """
    Carrega referências do disco.
    Retorna dict: symbol -> (price, saved_at)
    Ignora entradas mais antigas que REFERENCE_MAX_AGE_HOURS.
    """
    if not os.path.exists(REFERENCE_FILE):
        return {}
    try:
        with open(REFERENCE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = datetime.now(timezone.utc)
        result = {}
        for sym, entry in data.items():
            saved_at = datetime.fromisoformat(entry["saved_at"])
            age_hours = (now - saved_at).total_seconds() / 3600
            if age_hours <= REFERENCE_MAX_AGE_HOURS:
                result[sym] = (float(entry["price"]), saved_at)
            else:
                print(f"[INFO] {sym}: referência salva expirada ({age_hours:.1f}h), "
                      f"será usada abertura de 24h da Binance.")
        return result
    except Exception as e:
        print(f"[WARN] Erro ao carregar referências: {e}")
        return {}

# ─── Discord Client ───────────────────────────────────────────────────────────

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ─── Funções auxiliares ───────────────────────────────────────────────────────

def format_symbol(symbol: str) -> str:
    return symbol.replace("USDT", "")


def format_price(price: float) -> str:
    if price >= 1:
        return f"${price:,.2f}"
    return f"${price:.6f}"


def format_change(pct: float) -> str:
    arrow = "🟢 ▲" if pct > 0 else "🔴 ▼"
    return f"{arrow} {abs(pct):.2f}%"


async def fetch_ticker(session: aiohttp.ClientSession, symbol: str) -> dict | None:
    url = BINANCE_TICKER_URL.format(symbol=symbol)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.json()
            print(f"[WARN] {symbol}: HTTP {resp.status}")
            return None
    except Exception as e:
        print(f"[ERROR] Falha ao buscar {symbol}: {e}")
        return None


def build_alert_embed(
    symbol: str,
    current_price: float,
    ref_price: float,
    pct_change: float,
    ticker: dict,
    ref_age: str = "",
) -> discord.Embed:
    coin = format_symbol(symbol)
    is_up = pct_change > 0
    color = discord.Color.green() if is_up else discord.Color.red()
    direction = "SUBIU" if is_up else "CAIU"

    embed = discord.Embed(
        title=f"⚡ Alerta de Preço — {coin}",
        description=f"**{coin}** {direction} **{abs(pct_change):.2f}%** desde a referência!",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    ref_label = f"Preço Ref.{ref_age}"
    embed.add_field(name="Preço Atual", value=format_price(current_price), inline=True)
    embed.add_field(name=ref_label, value=format_price(ref_price), inline=True)
    embed.add_field(name="Variação", value=format_change(pct_change), inline=True)

    high_24h = float(ticker.get("highPrice", 0))
    low_24h = float(ticker.get("lowPrice", 0))
    change_24h = float(ticker.get("priceChangePercent", 0))
    volume_24h = float(ticker.get("quoteVolume", 0))

    embed.add_field(name="Máxima 24h", value=format_price(high_24h), inline=True)
    embed.add_field(name="Mínima 24h", value=format_price(low_24h), inline=True)
    embed.add_field(name="Variação 24h", value=format_change(change_24h), inline=True)
    embed.add_field(name="Volume 24h (USDT)", value=f"${volume_24h:,.0f}", inline=False)
    embed.set_footer(text="Binance • Monitoramento Mionions")
    return embed

# ─── Loop de monitoramento ────────────────────────────────────────────────────

@tasks.loop(seconds=CHECK_INTERVAL)
async def monitor_prices():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"[ERROR] Canal {CHANNEL_ID} não encontrado. Verifique o CHANNEL_ID no .env")
        return

    async with aiohttp.ClientSession() as session:
        fetches = [fetch_ticker(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*fetches)

    references_changed = False

    for symbol, ticker in zip(SYMBOLS, results):
        if ticker is None:
            continue

        current_price = float(ticker["lastPrice"])
        current_prices[symbol] = current_price
        last_tickers[symbol] = ticker

        # Primeira vez: define referência
        if symbol not in reference_prices:
            # Usa openPrice da Binance (preço de 24h atrás) como referência inicial
            open_price = float(ticker.get("openPrice", current_price))
            reference_prices[symbol] = open_price
            reference_timestamps[symbol] = datetime.now(timezone.utc) - timedelta(hours=24)
            references_changed = True
            pct_from_open = (current_price - open_price) / open_price * 100
            print(f"[INIT] {symbol} | abertura 24h: {format_price(open_price)} | "
                  f"atual: {format_price(current_price)} ({pct_from_open:+.2f}%)")
            continue

        ref_price = reference_prices[symbol]
        pct_change = (current_price - ref_price) / ref_price

        if abs(pct_change) >= ALERT_THRESHOLD:
            # Calcula há quanto tempo essa referência existe
            ref_ts = reference_timestamps.get(symbol)
            ref_age = ""
            if ref_ts:
                age = datetime.now(timezone.utc) - ref_ts
                h, m = divmod(int(age.total_seconds()) // 60, 60)
                ref_age = f" (há {h}h{m:02d}m)" if h else f" (há {m}m)"

            embed = build_alert_embed(
                symbol, current_price, ref_price, pct_change * 100, ticker, ref_age
            )
            try:
                await channel.send(embed=embed)
                print(f"[ALERTA] {symbol}: {pct_change:+.2f}%{ref_age} | "
                      f"{format_price(ref_price)} → {format_price(current_price)}")
                # Reseta referência para o preço atual após o alerta
                reference_prices[symbol] = current_price
                reference_timestamps[symbol] = datetime.now(timezone.utc)
                references_changed = True
            except discord.DiscordException as e:
                print(f"[ERROR] Falha ao enviar alerta para {symbol}: {e}")

    if references_changed:
        save_references()


@monitor_prices.before_loop
async def before_monitor():
    await client.wait_until_ready()

    # Carrega referências salvas antes do primeiro ciclo
    saved = load_references()
    for sym, (price, saved_at) in saved.items():
        if sym in SYMBOLS:
            reference_prices[sym] = price
            reference_timestamps[sym] = saved_at
            age_h = (datetime.now(timezone.utc) - saved_at).total_seconds() / 3600
            print(f"[LOAD] {sym}: referência restaurada {format_price(price)} "
                  f"(salva há {age_h:.1f}h)")

    print(f"[BOT] Online como {client.user}")
    print(f"[BOT] Ativos: {', '.join(format_symbol(s) for s in SYMBOLS)}")
    print(f"[BOT] Alerta em: ±{ALERT_THRESHOLD * 100:.0f}% | Checagem a cada {CHECK_INTERVAL}s")
    if saved:
        print(f"[BOT] {len(saved)} referência(s) restauradas do arquivo salvo.")
    else:
        print(f"[BOT] Sem arquivo salvo — referências iniciais serão o openPrice de 24h da Binance.")


# ─── Slash Commands ───────────────────────────────────────────────────────────

@tree.command(name="precos", description="Mostra os preços atuais de todos os ativos monitorados")
async def cmd_precos(interaction: discord.Interaction):
    if not current_prices:
        await interaction.response.send_message(
            "⏳ Ainda carregando preços, tente novamente em alguns segundos.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📊 Preços Atuais",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )

    for symbol in SYMBOLS:
        if symbol not in current_prices:
            continue
        coin = format_symbol(symbol)
        price = current_prices[symbol]
        ref = reference_prices.get(symbol, price)
        pct_vs_ref = (price - ref) / ref * 100 if ref else 0
        ticker = last_tickers.get(symbol, {})
        change_24h = float(ticker.get("priceChangePercent", 0))

        ref_ts = reference_timestamps.get(symbol)
        ref_age = ""
        if ref_ts:
            age = datetime.now(timezone.utc) - ref_ts
            h, m = divmod(int(age.total_seconds()) // 60, 60)
            ref_age = f"\nRef há: {h}h{m:02d}m" if h else f"\nRef há: {m}m"

        embed.add_field(
            name=coin,
            value=(
                f"{format_price(price)}\n"
                f"24h: {format_change(change_24h)}\n"
                f"vs Ref: {format_change(pct_vs_ref)}"
                f"{ref_age}"
            ),
            inline=True,
        )

    embed.set_footer(text=f"Binance • Threshold: ±{ALERT_THRESHOLD * 100:.0f}%")
    await interaction.response.send_message(embed=embed)


@tree.command(name="status", description="Mostra o status atual do bot de monitoramento")
async def cmd_status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Status do Bot",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Ativos Monitorados",
        value=", ".join(format_symbol(s) for s in SYMBOLS),
        inline=False,
    )
    embed.add_field(name="Threshold de Alerta", value=f"±{ALERT_THRESHOLD * 100:.0f}%", inline=True)
    embed.add_field(name="Intervalo de Checagem", value=f"{CHECK_INTERVAL}s", inline=True)
    embed.add_field(
        name="Loop Ativo",
        value="✅ Sim" if monitor_prices.is_running() else "❌ Não",
        inline=True,
    )
    ref_file_info = "✅ Existe" if os.path.exists(REFERENCE_FILE) else "❌ Não existe"
    embed.add_field(name="Arquivo de Referências", value=ref_file_info, inline=True)
    embed.set_footer(text="Binance • Monitoramento Mionions")
    await interaction.response.send_message(embed=embed)


@tree.command(name="resetref", description="Reseta o preço de referência de um ativo (ou todos)")
@app_commands.describe(ativo="Símbolo do ativo (ex: BTC) ou 'todos' para resetar tudo")
async def cmd_resetref(interaction: discord.Interaction, ativo: str = "todos"):
    ativo = ativo.upper()
    now = datetime.now(timezone.utc)

    if ativo == "TODOS":
        for sym in SYMBOLS:
            if sym in current_prices:
                reference_prices[sym] = current_prices[sym]
                reference_timestamps[sym] = now
        save_references()
        await interaction.response.send_message(
            "✅ Referências resetadas para o preço atual de todos os ativos.", ephemeral=True
        )
    else:
        symbol = ativo if ativo.endswith("USDT") else f"{ativo}USDT"
        if symbol not in SYMBOLS:
            await interaction.response.send_message(
                f"❌ `{ativo}` não está na lista de ativos monitorados.", ephemeral=True
            )
            return
        if symbol in current_prices:
            reference_prices[symbol] = current_prices[symbol]
            reference_timestamps[symbol] = now
            save_references()
            await interaction.response.send_message(
                f"✅ Referência de **{ativo}** resetada para {format_price(current_prices[symbol])}.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⏳ Preço de `{ativo}` ainda não carregado.", ephemeral=True
            )


@tree.command(name="crypto", description="Pesquisa o preço atual de qualquer criptomoeda")
@app_commands.describe(moeda="Nome ou símbolo da moeda (ex: BTC, ETH, DOGE, PEPE)")
async def cmd_crypto(interaction: discord.Interaction, moeda: str):
    await interaction.response.defer()

    moeda = moeda.strip().upper()
    symbol = moeda if moeda.endswith("USDT") else f"{moeda}USDT"

    async with aiohttp.ClientSession() as session:
        ticker = await fetch_ticker(session, symbol)

    if ticker is None:
        await interaction.followup.send(
            f"❌ Moeda **{moeda}** não encontrada na Binance.\n"
            f"Tente o símbolo exato (ex: `BTC`, `ETH`, `DOGE`, `SHIB`, `PEPE`).",
            ephemeral=True,
        )
        return

    coin = format_symbol(symbol)
    price = float(ticker["lastPrice"])
    high_24h = float(ticker.get("highPrice", 0))
    low_24h = float(ticker.get("lowPrice", 0))
    change_24h = float(ticker.get("priceChangePercent", 0))
    volume_24h = float(ticker.get("quoteVolume", 0))
    weighted_avg = float(ticker.get("weightedAvgPrice", 0))
    open_price = float(ticker.get("openPrice", 0))

    color = discord.Color.green() if change_24h >= 0 else discord.Color.red()

    embed = discord.Embed(
        title=f"🔍 {coin}/USDT",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Preço Atual", value=format_price(price), inline=True)
    embed.add_field(name="Abertura 24h", value=format_price(open_price), inline=True)
    embed.add_field(name="Variação 24h", value=format_change(change_24h), inline=True)
    embed.add_field(name="Máxima 24h", value=format_price(high_24h), inline=True)
    embed.add_field(name="Mínima 24h", value=format_price(low_24h), inline=True)
    embed.add_field(name="Média Ponderada", value=format_price(weighted_avg), inline=True)
    embed.add_field(name="Volume 24h (USDT)", value=f"${volume_24h:,.0f}", inline=False)

    monitored = "✅ Monitorado" if symbol in SYMBOLS else "⚠️ Não monitorado"
    embed.set_footer(text=f"Binance • {monitored}")

    await interaction.followup.send(embed=embed)


# ─── Eventos Discord ──────────────────────────────────────────────────────────

@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"[BOT] Slash commands sincronizados no servidor (instantâneo).")
    else:
        await tree.sync()
        print(f"[BOT] Slash commands sincronizados globalmente (pode levar até 1h).")
    if not monitor_prices.is_running():
        monitor_prices.start()


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN não definido no .env")
    if CHANNEL_ID == 0:
        raise RuntimeError("CHANNEL_ID não definido no .env")

    client.run(DISCORD_TOKEN)
