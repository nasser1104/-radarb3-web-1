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
from datetime import datetime
import re

# ================= CONFIGURAÇÕES =================
TOKEN = "7777625610:AAGZtOr9oLXIzbb2BnckEoFdsX8uzmAkDYI"
PORT = 8080  # Porta fixa obrigatória para o Render
TIMEZONE = pytz.timezone('America/Sao_Paulo')

# ================= DADOS =================
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

# ================= ANÁLISE LEVE =================
class Analisador:
    @staticmethod
    def analisar_sentimento(titulo):
        """Análise por palavras-chave (substitui o transformers)"""
        palavras_positivas = ['alta', 'lucro', 'crescimento', 'compra', 'melhora', 'forte']
        palavras_negativas = ['queda', 'perda', 'venda', 'fraco', 'corte', 'redução']
        
        score = 0
        titulo = titulo.lower()
        
        for palavra in palavras_positivas:
            if palavra in titulo:
                score += 1
                
        for palavra in palavras_negativas:
            if palavra in titulo:
                score -= 1
                
        if score > 0:
            return "ALTA", min(0.99, score/len(palavras_positivas))
        elif score < 0:
            return "BAIXA", min(0.99, abs(score)/len(palavras_negativas))
        else:
            return "NEUTRO", 0.5

# ================= SERVIDOR =================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Ações B3 Online"

@app.route('/health')
def health_check():
    return {"status": "online"}, 200

def run_flask():
    serve(app, host="0.0.0.0", port=PORT)

# ================= FUNÇÕES DO BOT =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 *Bot de Ações B3*\n\n"
        "Envie /acao [TICKER] para análise\n"
        "Ex: /acao PETR4\n\n"
        "Monitorando 50 ações em 8 fontes 24/7",
        parse_mode='Markdown'
    )

async def analisar_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ticker = update.message.text.split()[1].upper() if len(update.message.text.split()) > 1 else None
        
        if not ticker or ticker not in ACOES_B3:
            await update.message.reply_text("❌ Use: /acao [TICKER]\nEx: /acao PETR4")
            return
            
        # Dados da ação
        dados = yf.Ticker(f"{ticker}.SA").history(period="1d")
        preco = dados['Close'].iloc[-1]
        variacao = ((dados['Close'].iloc[-1] - dados['Open'].iloc[-1]) / dados['Open'].iloc[-1]) * 100
        
        # Busca notícias
        noticias = []
        for site, url in FONTES_NOTICIAS.items():
            try:
                response = requests.get(url, timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for noticia in soup.find_all('a', href=True)[:2]:
                    titulo = noticia.get_text(strip=True)
                    if ticker.lower() in titulo.lower():
                        link = noticia['href'] if noticia['href'].startswith('http') else f"{url}{noticia['href']}"
                        sentimento, confianca = Analisador.analisar_sentimento(titulo)
                        noticias.append({
                            'titulo': titulo,
                            'link': link,
                            'fonte': site,
                            'sentimento': sentimento,
                            'confianca': confianca
                        })
            except:
                continue
        
        # Ordena por confiança
        noticias = sorted(noticias, key=lambda x: x['confianca'], reverse=True)[:3]
        
        # Monta resposta
        msg = f"📊 *{ticker}* - R$ {preco:.2f} ({variacao:+.2f}%)\n\n"
        
        if noticias:
            msg += "📌 *Principais notícias:*\n"
            for n in noticias:
                msg += f"▪️ [{n['fonte']}]({n['link']}): {n['titulo']}\n"
                msg += f"   → *{n['sentimento']}* (Confiança: {n['confianca']*100:.0f}%)\n\n"
        else:
            msg += "ℹ️ Nenhuma notícia recente encontrada\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Erro ao processar: {str(e)}")

async def alertas_automaticos(context: ContextTypes.DEFAULT_TYPE):
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
                            sentimento, confianca = Analisador.analisar_sentimento(titulo)
                            
                            if confianca > 0.7:  # Só alerta se alta confiança
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
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("acao", analisar_acao))
    
    # Agendador de alertas (a cada 2 horas)
    if hasattr(application, 'job_queue'):
        application.job_queue.run_repeating(
            alertas_automaticos,
            interval=7200,  # 2 horas
            first=10
        )
    
    # Inicia servidor Flask em thread separada
    Thread(target=run_flask).start()
    
    print("🟢 Bot iniciado com sucesso!")
    application.run_polling()

if __name__ == '__main__':
    main()