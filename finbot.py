import discord
from discord.ext import commands
import yfinance as yf
import datetime
import finnhub
import google.generativeai as genai
import asyncio
import re
import json

DISCORD_TOKEN = "YOUR TOKEN HERE "
FINNHUB_KEY = "YOUR API HERE"
GEMINI_KEY = "YOUR LANGUAGE MODEL HERE"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- HELPERS ----------------
def is_finance_related(text: str) -> bool:
    finance_patterns = [
        r"\b(stock|stocks|equity|equities|share|shares|price|quote|market|markets|index|indices)\b",
        r"\b(bond|bonds|yield|etf|fund|crypto|bitcoin|ethereum|token|fx|forex|currency)\b",
        r"\b(usd|eur|gbp|dividend|earnings|guidance|revenue|profit|loss|valuation|pe|p\/e)\b",
        r"\b(volatility|options|call|put|derivative|hedge|portfolio|trading|invest|investment)\b",
        r"\b(macro|federal reserve|fed|inflation|cpi|ppi|gdp|jobs|economy|economic)\b",
        r"\b(impact|affect|affecting|influence|effect|implications|outlook|forecast)\b.*\b(company|business|stock|market|price|valuation|revenue)\b",
        r"\b(news|announcement|report|earnings|financial|performance)\b.*\b(impact|affect|influence)\b",
        r"\bhow.*\b(company|stock|market|business|price|valuation|revenue|earnings)\b",
        r"\b(microsoft|apple|google|amazon|tesla|meta|nvidia|companies)\b.*\b(impact|affect|stock|price|market|business)\b",
        r"\b(bullish|bearish|buy|sell|hold|rating|upgrade|downgrade|target|analyst)\b"
    ]
    
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in finance_patterns)

def extract_possible_tickers(text: str):
    candidates = re.findall(r"\b[A-Z]{1,5}(?:-[A-Z]{1,4})?\b", text)
    blacklist = {"USD", "ETF", "GDP", "CPI", "PPI", "EPS", "YOY", "QOQ"}
    return [c for c in candidates if c not in blacklist]

def deduplicate_news(news_list):
    seen = set()
    deduped = []
    for item in news_list:
        headline = item.get("headline", "").strip()
        if headline and headline not in seen:
            seen.add(headline)
            deduped.append(item)
    return deduped

async def send_rich_news_format(user: discord.User, news_list: list):
    """Send news in rich embed format with images and descriptions"""
    try:
        for article in news_list:
            embed = discord.Embed(
                title=article.get('headline', 'No headline')[:256],  # Discord title limit
                url=article.get('url', ''),
                description=article.get('summary', '')[:4096] if article.get('summary') else 'No description available',
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcfromtimestamp(article.get('datetime', 0))
            )
            

            if article.get('image'):
                embed.set_image(url=article.get('image'))
            
            if article.get('source'):
                embed.add_field(name="Source", value=article.get('source'), inline=True)
            
            if article.get('category'):
                embed.add_field(name="Category", value=article.get('category'), inline=True)
            
            embed.set_footer(text="Finbot News • Built by Umar")
            
            await user.send(embed=embed)
            
            await asyncio.sleep(0.5)
            
    except Exception as e:
        await user.send(f"Error displaying rich news format: {e}")
        for article in news_list[:5]:  # Limit to 5 to avoid spam
            dt = datetime.datetime.utcfromtimestamp(article.get("datetime", 0)).strftime("%Y-%m-%d %H:%M UTC")
            headline = article.get('headline', 'No headline')
            url = article.get('url', 'No URL')
            await user.send(f"📰 **{headline}**\n🔗 {url}\n⏰ {dt}\n")

async def send_market_info_embed(user: discord.User, ticker_symbol: str):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        name = info.get('shortName', ticker_symbol)
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose')
        day_low = info.get('dayLow')
        day_high = info.get('dayHigh')
        market_cap = info.get('marketCap')
        volume = info.get('volume')
        sector = info.get('sector', 'N/A')
        industry = info.get('industry', 'N/A')
        website = info.get('website', 'N/A')

        embed = discord.Embed(
            title=f"Market Info for {name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Price", value=f"${current_price if current_price else 'N/A'}", inline=True)
        embed.add_field(name="Previous Close", value=f"${prev_close if prev_close else 'N/A'}", inline=True)
        embed.add_field(name="Day's Range", value=f"${day_low if day_low else 'N/A'} - ${day_high if day_high else 'N/A'}", inline=False)
        embed.add_field(name="Market Cap", value=f"${market_cap:,}" if market_cap else "N/A", inline=True)
        embed.add_field(name="Volume", value=f"{volume:,}" if volume else "N/A", inline=True)
        embed.add_field(name="Sector", value=sector, inline=True)
        embed.add_field(name="Industry", value=industry, inline=True)
        embed.add_field(name="Website", value=website, inline=False)
        embed.set_footer(text="Finbot • Built by Umar")
        await user.send(embed=embed)
    except Exception as e:
        await user.send(f"Could not fetch market info for {ticker_symbol}: {e}")

async def fetch_finnhub_company_news(symbol: str, days: float):
    try:
        client = finnhub.Client(api_key=FINNHUB_KEY)
        end_date = datetime.datetime.utcnow()
        start_date = end_date - datetime.timedelta(days=days)
        return client.company_news(
            symbol,
            _from=start_date.strftime("%Y-%m-%d"),
            to=end_date.strftime("%Y-%m-%d")
        ) or []
    except Exception as e:
        print(f"Error fetching news for {symbol}: {e}")
        return []

async def live_data_answer(symbol: str) -> str:
    try:
        client = finnhub.Client(api_key=FINNHUB_KEY)
        q = client.quote(symbol)
        c = q.get("c"); pc = q.get("pc"); d = q.get("d"); dp = q.get("dp"); h = q.get("h"); l = q.get("l")
        return (
            f"{symbol} — price ${c if c else 'N/A'} "
            f"(Δ {('+' if (d or 0) >= 0 else '')}{d if d else 'N/A'}, "
            f"{('+' if (dp or 0) >= 0 else '')}{dp if dp else 'N/A'}%). "
            f"Day range: ${l if l else 'N/A'}–${h if h else 'N/A'}. "
            f"Prev close: ${pc if pc else 'N/A'}."
        )
    except Exception as e:
        return f"Couldn't retrieve live data for {symbol}: {e}"

async def gemini_answer(question: str, news_context: list, default_symbol: str, days: float) -> str:
    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        ctx = json.dumps(news_context[:15])
        prompt = f"""
You are a finance assistant analyzing market news and business impacts. The user will ask questions about recent news, market trends, and how developments affect companies.

Use the provided news JSON as context to answer questions about:
- How news impacts specific companies or sectors
- Market implications of recent developments
- Business analysis and outlook based on news
- Company performance and competitive positioning

The news covers approximately the last {days} days for {default_symbol} and related companies.

ONLY say "USE_FINNHUB [SYMBOL]" if the user specifically asks for current/live price data, quotes, or real-time market numbers.

For analytical questions about business impact, market implications, or news analysis, provide detailed insights based on the news context.

News context JSON:
{ctx}

User question: {question}

Provide a comprehensive analysis based on the news context. Focus on business implications, market impact, and strategic insights.
"""
        resp = model.generate_content(prompt)
        return resp.text.strip() if getattr(resp, "text", "").strip() else "I don't have enough information to provide a detailed analysis right now."
    except Exception as e:
        return f"Error getting AI response: {e}"

class AssetChoiceView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Stocks", style=discord.ButtonStyle.primary, emoji="📈")
    async def stocks_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        stock_options = [
            ("Apple Inc.", "AAPL"),
            ("Microsoft Corporation", "MSFT"),
            ("Alphabet Inc.", "GOOGL"),
            ("Amazon.com, Inc.", "AMZN"),
            ("Tesla, Inc.", "TSLA"),
            ("Meta Platforms, Inc.", "META"),
            ("NVIDIA Corporation", "NVDA"),
            ("Berkshire Hathaway Inc.", "BRK-B"),
        ]
        await interaction.response.send_message(
            "Which stock do you want to track?",
            view=NewsChoiceView(self.user_id, stock_options),
            ephemeral=True
        )

    @discord.ui.button(label="Crypto", style=discord.ButtonStyle.secondary, emoji="🪙")
    async def crypto_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        crypto_options = [
            ("Bitcoin", "BTC-USD"),
            ("Ethereum", "ETH-USD"),
            ("Binance Coin", "BNB-USD"),
            ("XRP", "XRP-USD"),
            ("Cardano", "ADA-USD"),
            ("Solana", "SOL-USD"),
            ("Dogecoin", "DOGE-USD"),
            ("Polkadot", "DOT-USD"),
        ]
        await interaction.response.send_message(
            "Which crypto do you want to track?",
            view=NewsChoiceView(self.user_id, crypto_options),
            ephemeral=True
        )

class NewsChoiceView(discord.ui.View):
    def __init__(self, user_id: int, options: list):
        super().__init__(timeout=180)
        self.user_id = user_id
        for label, ticker in options:
            self.add_item(NewsChoiceView.NewsButton(label, ticker, self))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    class NewsButton(discord.ui.Button):
        def __init__(self, label: str, ticker: str, parent_view: 'NewsChoiceView'):
            super().__init__(label=label, style=discord.ButtonStyle.secondary)
            self.ticker = ticker
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.user_id:
                return await interaction.response.send_message("Not your session.", ephemeral=True)
            await interaction.response.send_message(
                f"Select duration for {self.label}:",
                view=DurationChoiceView(self.parent_view.user_id, self.ticker),
                ephemeral=True
            )

class DurationChoiceView(discord.ui.View):
    DURATIONS = {
        "6 Hours": 0.25,
        "3 Days": 3,
        "7 Days": 7,
        "14 Days": 14
    }

    def __init__(self, user_id: int, ticker: str):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.ticker = ticker
        for label in self.DURATIONS.keys():
            self.add_item(DurationChoiceView.DurationButton(label, self))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    class DurationButton(discord.ui.Button):
        def __init__(self, label: str, parent_view: 'DurationChoiceView'):
            super().__init__(label=label, style=discord.ButtonStyle.primary)
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.user_id:
                return await interaction.response.send_message("Not your session.", ephemeral=True)

            days = DurationChoiceView.DURATIONS[self.label]
            await interaction.response.send_message(
                f"Fetching news for {self.parent_view.ticker} over {self.label}...",
                ephemeral=False
            )
            try:
                await send_full_dm_package(interaction.user, self.parent_view.ticker, days)
                await interaction.followup.send("Information sent to your DMs!", ephemeral=False)
            except Exception as e:
                await interaction.followup.send(f"Error sending information: {e}", ephemeral=True)


async def send_full_dm_package(user: discord.User, ticker_symbol: str, days: float):
    try:

        await send_market_info_embed(user, ticker_symbol)


        news = await fetch_finnhub_company_news(ticker_symbol, days)
        news = deduplicate_news(news)

        if not news:
            await user.send(f"No news found for {ticker_symbol} in the last {days} days.")
        else:
            await user.send(f"📰 Latest news for {ticker_symbol} (last {days} days):")
            await send_rich_news_format(user, news[:10])


        await user.send("If you have questions please ask — you have 10 min")
        await start_qa_session(user, news, ticker_symbol, days)
    except Exception as e:
        await user.send(f"Error sending package: {e}")

async def start_qa_session(user: discord.User, news_context: list, ticker_symbol: str, days: float):
    end_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)

    def dm_check(m: discord.Message):
        return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

    while datetime.datetime.utcnow() < end_time:
        try:
            msg = await bot.wait_for("message", timeout=60, check=dm_check)
        except asyncio.TimeoutError:
            continue

        content = msg.content.strip()
        if not content:
            continue
            
        if not is_finance_related(content):
            await user.send("Please keep questions related to finance, markets, or business impact.")
            continue

        wants_live = bool(re.search(r"\b(price|quote|now|current|live|today|right now|latest price|current price)\b", content, re.IGNORECASE))
        mentioned = extract_possible_tickers(content)
        symbol_to_use = mentioned[0] if mentioned else ticker_symbol


        if wants_live:
            live = await live_data_answer(symbol_to_use)
            await user.send(live)
            continue


        ans = await gemini_answer(content, news_context, ticker_symbol, days)
        

        if "USE_FINNHUB" in ans:
            hinted = extract_possible_tickers(ans)
            sym = hinted[0] if hinted else symbol_to_use
            live = await live_data_answer(sym)
            await user.send(live)
        else:

            if len(ans) > 2000:

                chunks = []
                current_chunk = ""
                

                lines = ans.split('\n')
                for line in lines:
                    if len(current_chunk + line + '\n') > 1900:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = line + '\n'
                        else:
                            chunks.append(line[:1900] + '...')
                            current_chunk = '...' + line[1900:] + '\n'
                    else:
                        current_chunk += line + '\n'
                
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # Send chunks with indicators
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await user.send(chunk)
                    else:
                        await user.send(f"**(continued...)**\n{chunk}")
                    # Small delay between messages
                    await asyncio.sleep(0.5)
            else:
                await user.send(ans)

    await user.send("Q&A session ended.")


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.content.strip().lower() == "ready":
        embed = discord.Embed(
            title="What are we tracking today?",
            description="Choose Stocks or Crypto to begin tracking and get news.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Finbot • Built by Umar")
        view = AssetChoiceView(user_id=message.author.id)
        await message.channel.send(embed=embed, view=view)
    await bot.process_commands(message)

@bot.event
async def on_error(event, *args, **kwargs):
    print(f"An error occurred in {event}: {args}, {kwargs}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.command()
async def help_finance(ctx):
    """Show help information for the finance bot"""
    embed = discord.Embed(
        title="Finance Bot Help",
        description="Type 'ready' to start tracking stocks or crypto!",
        color=discord.Color.green()
    )
    embed.add_field(name="Commands", value="!ping - Test bot response\n!help_finance - Show this help", inline=False)
    embed.set_footer(text="Finbot • Built by Umar")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)