
import os
import warnings
warnings.filterwarnings("ignore")

from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import yfinance as yf
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import pytz
import threading
import asyncio

TOKEN = "7777625610:AAGZtOr9oLXIzbb2BnckEoFdsX8uzmAkDYI"
TIMEZONE = pytz.timezone('America/Sao_Paulo')

ACOES_B3 = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "B3SA3", "ABEV3", "BBAS3", "PETR3", 
    "ITSA4", "WEGE3", "JBSS3", "RENT3", "BPAC11", "SUZB3", "ELET3", "BBDC3",
    "HAPV3", "GGBR4", "VALE5", "ITUB3", "LREN3", "RAIL3", "NTCO3", "BBSE3",
    "EQTL3", "UGPA3", "CIEL3", "CSNA3", "KLBN11", "SBSP3", "MGLU3", "BRFS3",
    "EMBR3", "TOTS3", "CYRE3", "BRDT3", "BRML3", "QUAL3", "CCRO3", "VIVT3",
    "RADL3", "ENBR3", "PRIO3", "IRBR3", "MRFG3", "TAEE11", "GOAU4", "BEEF3",
    "ECOR3", "BRAP4", "EGIE3", "CRFB3", "TIMS3", "MRVE3", "AZUL4", "YDUQ3",
    "MULT3", "COGN3", "CVCB3", "LAME4", "PCAR3", "BRKM5", "SULA11", "SANB11",
    "HYPE3", "FLRY3", "LWSA3", "CPLE6", "CPFE3", "BRSR6", "GOLL4", "SLCE3",
    "USIM5", "DXCO3", "VULC3", "RRRP3", "ALPA4", "CMIG4", "JHSF3", "ELET6",
    "SOMA3", "GRND3", "CASH3", "TUPY3", "SMTO3", "ARZZ3", "IGTA3", "EZTC3",
    "LEVE3", "ALSO3", "ENGI11", "ASAI3", "BTOW3", "MOVI3", "AERI3", "BLAU3",
    "GMAT3", "VIIA3", "POSI3", "CSAN3", "RECV3", "AURE3", "TRPL4", "PTBL3"
]

FONTES_NOTICIAS = {
    "InfoMoney": "https://www.infomoney.com.br/ultimas-noticias/",
    "Investing": "https://br.investing.com/news/stock-market-news",
    "Valor": "https://valor.globo.com/financas/",
    "Reuters": "https://www.reuters.com.br/",
    "CNN": "https://www.cnnbrasil.com.br/economia/",
    "Suno": "https://www.suno.com.br/noticias/",
    "MoneyTimes": "https://www.moneytimes.com.br/ultimas-noticias/"
}

PALAVRAS_POSITIVAS = ["lucro", "alta", "crescimento", "recorde", "expansão", "positivo"]
PALAVRAS_NEGATIVAS = ["queda", "prejuízo", "perda", "baixa", "crise", "negativo"]

app = Flask(__name__)

@app.route("/")
def home():
    return "RadarB3 online e rodando com polling!"

def analisar_sentimento(texto):
    texto = texto.lower()
    positivos = sum(p in texto for p in PALAVRAS_POSITIVAS)
    negativos = sum(n in texto for n in PALAVRAS_NEGATIVAS)
    if positivos > negativos:
        return "alta", positivos / (positivos + negativos + 1)
    elif negativos > positivos:
        return "baixa", negativos / (positivos + negativos + 1)
    return "neutro", 0.5

async def buscar_noticias():
    resultados = []
    for fonte, url in FONTES_NOTICIAS.items():
        try:
            html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
            soup = BeautifulSoup(html, 'html.parser')
            links = soup.find_all('a', href=True)[:20]
            for link in links:
                titulo = link.get_text(strip=True)
                for acao in ACOES_B3:
                    if acao in titulo:
                        resultados.append({
                            "acao": acao,
                            "titulo": titulo,
                            "link": link["href"] if link["href"].startswith("http") else url + link["href"],
                            "fonte": fonte
                        })
                        break
        except:
            continue
    return resultados

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ RadarB3 Ativo!\nEnvie o código de uma ação como: PETR4")

async def handle_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    acao = update.message.text.upper().strip()
    if acao not in ACOES_B3:
        await update.message.reply_text("❌ Ação não encontrada.")
        return
    try:
        preco = yf.Ticker(f"{acao}.SA").history(period="1d")['Close'].iloc[-1]
        noticias = await buscar_noticias()
        relacionadas = [n for n in noticias if n["acao"] == acao][:3]
        msg = f"📊 {acao} - R$ {preco:.2f}\n\n"
        for n in relacionadas:
            impacto, confianca = analisar_sentimento(n["titulo"])
            msg += f"▪️ {n['fonte']}: {n['titulo']}\n→ Impacto: {impacto.upper()} (Confiança: {int(confianca*100)}%)\n\n"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro: {str(e)}")

def rodar_telegram():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app_telegram = ApplicationBuilder().token(TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_acao))
    print("📡 Telegram polling iniciado.")
    app_telegram.run_polling()

def main():
    threading.Thread(target=rodar_telegram, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()
