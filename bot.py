import os
import warnings
warnings.filterwarnings("ignore")

from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    JobQueue
)
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests
from transformers import pipeline
import pytz
from threading import Thread
from waitress import serve
import numpy as np

# Configurações
TOKEN = "7777625610:AAGZtOr9oLXIzbb2BnckEoFdsX8uzmAkDYI"
PORT = int(os.getenv("PORT", 8080))
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# 50 ações mais líquidas (otimizado para plano free)
ACOES_B3 = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", "ABEV3", "BBAS3", "PETR3",
    "ITSA4", "WEGE3", "JBSS3", "RENT3", "BPAC11", "SUZB3", "ELET3", "BBDC3",
    "HAPV3", "GGBR4", "LREN3", "RAIL3", "NTCO3", "BBSE3", "EQTL3", "UGPA3",
    "CIEL3", "CSNA3", "MGLU3", "BRFS3", "EMBR3", "TOTS3", "CYRE3", "GOAU4",
    "PRIO3", "TAEE11", "CRFB3", "HYPE3", "BRKM5", "QUAL3", "RADL3", "ENBR3",
    "MRFG3", "IRBR3", "ECOR3", "BRAP4", "EGIE3", "COGN3", "CVCB3", "PCAR3",
    "BRML3", "VIVT3"
]

# 7 sites otimizados
FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Investing": "https://br.investing.com/news/stock-market-news",
    "Valor": "https://valor.globo.com/financas/",
    "TradersClub": "https://www.tradersclub.com.br/noticias",
    "MoneyTimes": "https://www.moneytimes.com.br/ultimas-noticias/",
    "Sunoresearch": "https://sunoresearch.com.br/noticias/",
    "UOL Economia": "https://economia.uol.com.br/ultimas/"
}

# Análise de Sentimento Leve
class AnalisadorSentimentos:
    def __init__(self):
        self.modelo = pipeline(
            "text-classification",
            model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
            device=-1
        )
    
    def analisar(self, texto):
        try:
            resultado = self.modelo(texto[:512])[:1]  # Limita tamanho para economizar memória
            return {
                'sentimento': resultado[0]['label'],
                'confianca': resultado[0]['score']
            }
        except:
            return {'sentimento': 'NEUTRO', 'confianca': 0.5}

# Servidor Web
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Ações B3 Online"

def run_flask():
    serve(app, host="0.0.0.0", port=PORT)

# Funções do Bot
analisador = AnalisadorSentimentos()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 *Bot de Ações B3*\n\n"
        "Envie /acao [TICKER] para análise\n"
        "Ex: /acao PETR4\n\n"
        "Monitorando 50 ações 24/7",
        parse_mode='Markdown'
    )

async def analisar_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ticker = context.args[0].upper() if context.args else None
        if not ticker or ticker not in ACOES_B3:
            await update.message.reply_text("❌ Use: /acao [TICKER]\nEx: /acao PETR4")
            return
        
        # Dados da ação
        dados = yf.Ticker(f"{ticker}.SA").history(period="2d")
        preco = dados['Close'].iloc[-1]
        variacao = ((dados['Close'].iloc[-1] - dados['Close'].iloc[-2]) / dados['Close'].iloc[-2]) * 100
        
        # Busca notícias
        noticias = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for noticia in soup.find_all('a', href=True)[:2]:
                    titulo = noticia.get_text(strip=True)
                    if ticker.lower() in titulo.lower():
                        link = noticia['href'] if noticia['href'].startswith('http') else f"{url}{noticia['href']}"
                        noticias.append({'titulo': titulo, 'link': link, 'fonte': site})
            except:
                continue
        
        # Análise
        analise = analisador.analisar(noticias[0]['titulo']) if noticias else {'sentimento': 'NEUTRO', 'confianca': 0.5}
        
        # Monta resposta
        msg = (
            f"📊 *{ticker}* - R$ {preco:.2f} ({variacao:+.2f}%)\n"
            f"📌 *Tendência*: {analise['sentimento']} ({analise['confianca']*100:.0f}%)\n\n"
        )
        
        if noticias:
            msg += "📰 *Notícias recentes:*\n"
            for n in noticias[:3]:
                msg += f"▪️ [{n['fonte']}]({n['link']}): {n['titulo']}\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro: {str(e)}")

async def monitorar_noticias(context: ContextTypes.DEFAULT_TYPE):
    try:
        for ticker in ACOES_B3[:15]:  # Verifica 15 ações por ciclo
            noticias = []
            for url in list(FONTES_NOTICIAS.values())[:3]:  # Verifica 3 sites por ciclo
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    response = requests.get(url, headers=headers, timeout=5)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    for noticia in soup.find_all('a', href=True)[:1]:
                        titulo = noticia.get_text(strip=True)
                        if ticker.lower() in titulo.lower():
                            link = noticia['href'] if noticia['href'].startswith('http') else f"{url}{noticia['href']}"
                            analise = analisador.analisar(titulo)
                            if analise['confianca'] > 0.7:
                                await context.bot.send_message(
                                    chat_id=context.job.chat_id,
                                    text=f"🚨 *{ticker}*: {titulo}\n📌 {analise['sentimento']} ({analise['confianca']*100:.0f}%)\n🔗 {link}",
                                    parse_mode='Markdown'
                                )
                                await asyncio.sleep(1)
                except:
                    continue
    except:
        pass

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("acao", analisar_acao))
    
    if application.job_queue:
        application.job_queue.run_repeating(
            monitorar_noticias,
            interval=3600,
            first=10
        )
    
    Thread(target=run_flask).start()
    application.run_polling()

if __name__ == '__main__':
    main()