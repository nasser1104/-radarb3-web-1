import os
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    filters
)
import yfinance as yf
from threading import Thread
from waitress import serve
import pytz
from datetime import datetime, timedelta
import re

# Configurações
TOKEN = "7777625610:AAGZtOr9oLXIzbb2BnckEoFdsX8uzmAkDYI"
PORT = 8080
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# Dados reduzidos para 50 ações
ACOES_B3 = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", "ABEV3", "BBAS3", "PETR3",
    "ITSA4", "WEGE3", "JBSS3", "RENT3", "BPAC11", "SUZB3", "ELET3", "BBDC3",
    "HAPV3", "GGBR4", "LREN3", "RAIL3", "NTCO3", "BBSE3", "EQTL3", "UGPA3",
    "CIEL3", "CSNA3", "MGLU3", "BRFS3", "EMBR3", "TOTS3", "CYRE3", "GOAU4",
    "PRIO3", "TAEE11", "CRFB3", "HYPE3", "BRKM5", "QUAL3", "RADL3", "ENBR3",
    "MRFG3", "IRBR3", "ECOR3", "BRAP4", "EGIE3", "COGN3", "CVCB3", "PCAR3",
    "BRML3", "VIVT3"
]

FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Investing": "https://br.investing.com/news/stock-market-news",
    "Valor": "https://valor.globo.com/financas/",
    "TradersClub": "https://www.tradersclub.com.br/noticias",
    "MoneyTimes": "https://www.moneytimes.com.br/ultimas-noticias/",
    "Sunoresearch": "https://sunoresearch.com.br/noticias/",
    "UOL Economia": "https://economia.uol.com.br/ultimas/",
    "CNN Brasil": "https://www.cnnbrasil.com.br/economia/"
}

# Análise leve
class Analisador:
    @staticmethod
    def analisar(titulo):
        positivas = ['alta', 'lucro', 'crescimento', 'compra', 'melhora']
        negativas = ['queda', 'perda', 'venda', 'fraco', 'corte']
        
        score = sum(1 for p in positivas if p in titulo.lower()) - sum(1 for n in negativas if n in titulo.lower())
        
        if score > 0:
            return "ALTA", min(0.99, score/5)
        elif score < 0:
            return "BAIXA", min(0.99, abs(score)/5)
        else:
            return "NEUTRO", 0.5

# Servidor
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Ações B3 Online"

@app.route('/health')
def health():
    return {"status": "online"}, 200

def run_flask():
    serve(app, host='0.0.0.0', port=PORT)

# Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ *RadarB3 Ativo!*\n"
        "Envie o código de uma ação como: PETR4",
        parse_mode='Markdown'
    )

async def handle_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ticker = update.message.text.upper()
        if ticker not in ACOES_B3:
            await update.message.reply_text("❌ Ação inválida. Use /start para ajuda")
            return
        
        # Dados da ação com tratamento de erro
        dados = yf.Ticker(f"{ticker}.SA").history(period="2d")
        if dados.empty or len(dados) < 2:
            await update.message.reply_text(f"⚠️ Dados temporariamente indisponíveis para {ticker}")
            return
            
        preco = dados['Close'].iloc[-1]
        variacao = ((dados['Close'].iloc[-1] - dados['Close'].iloc[-2]) / dados['Close'].iloc[-2]) * 100
        
        # Notícias
        noticias = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                response = requests.get(url, timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for noticia in soup.find_all('a', href=True)[:2]:
                    titulo = noticia.get_text(strip=True)
                    if ticker.lower() in titulo.lower():
                        link = noticia['href'] if noticia['href'].startswith('http') else f"{url}{noticia['href']}"
                        sentimento, confianca = Analisador.analisar(titulo)
                        noticias.append({
                            'titulo': titulo,
                            'link': link,
                            'fonte': site,
                            'sentimento': sentimento,
                            'confianca': confianca
                        })
            except:
                continue
        
        # Monta resposta
        msg = f"📊 *{ticker}* - R$ {preco:.2f} ({variacao:+.2f}%)\n\n"
        
        if noticias:
            msg += "📌 *Notícias recentes:*\n"
            for n in sorted(noticias, key=lambda x: x['confianca'], reverse=True)[:3]:
                msg += f"▪️ [{n['fonte']}]({n['link']}): {n['titulo']}\n"
                msg += f"   → *{n['sentimento']}* (Confiança: {n['confianca']*100:.0f}%)\n\n"
        else:
            msg += "ℹ️ Nenhuma notícia recente encontrada\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro ao processar: {str(e)}")

async def alertas(context: ContextTypes.DEFAULT_TYPE):
    try:
        for ticker in ACOES_B3[:10]:  # Verifica 10 ações por ciclo
            for site, url in FONTES_NOTICIAS.items():
                try:
                    response = requests.get(url, timeout=3)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    for noticia in soup.find_all('a', href=True)[:1]:
                        titulo = noticia.get_text(strip=True)
                        if ticker.lower() in titulo.lower():
                            link = noticia['href'] if noticia['href'].startswith('http') else f"{url}{noticia['href']}"
                            sentimento, confianca = Analisador.analisar(titulo)
                            
                            if confianca > 0.7:
                                await context.bot.send_message(
                                    chat_id=context.job.chat_id,
                                    text=f"🚨 *{ticker}*: {titulo}\n📌 {sentimento} ({confianca*100:.0f}%)\n🔗 {link}",
                                    parse_mode='Markdown',
                                    disable_web_page_preview=True
                                )
                                await asyncio.sleep(1)
                except:
                    continue
    except:
        pass

def main():
    # Configuração única do bot
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_acao))
    
    # Job único
    if hasattr(application, 'job_queue'):
        application.job_queue.run_repeating(
            alertas,
            interval=7200,  # 2 horas
            first=5
        )
    
    # Inicia servidor em thread
    Thread(target=run_flask, daemon=True).start()
    
    print("🟢 Bot iniciado com sucesso!")
    application.run_polling(
        drop_pending_updates=True,  # Evita conflitos de instância
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == '__main__':
    main()