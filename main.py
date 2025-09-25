import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel
from typing import Dict, List, Any


from models.models import init_db
from handlers import requests as rq
from handlers.work_with_GoogleTable import GoogleSheetsService
from handlers.balance_formation import GoogleSheetsBalanceUpdater

######### проверка обновления


@asynccontextmanager
async def lifespan(app_: FastAPI):
    await init_db()
    yield


#app = FastAPI(title="web_app_tg", lifespan=lifespan)
app = FastAPI(title="web_app_tg", lifespan=lifespan) # инициализации в add.py, lifespan не вызываю
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tg-app-hcl.web.app",  # Ваш Firebase Hosting URL
        "http://www.cbr.ru",
        "http://127.0.0.1:8000"
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_credentials=True,
    allow_headers=["*"],
)

service_GoogleSheet_Ledger = GoogleSheetsService()
service_GoogleSheet_Balances = GoogleSheetsBalanceUpdater()


import os

from dotenv import find_dotenv, load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage


load_dotenv(find_dotenv())

bot = Bot(token=os.getenv('TOKEN_Lora'))

TELEGRAM_CHAT_ID = os.getenv('telegram_chat_id')

from aiogram import Router

router = Router()
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Запуск бота Lora, является админом в группе
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling())


# Глобальная переменная для хранения структуры таблицы
table_structure = {}

@app.get("/")
async def root():
    return {"message": "Привет"}

from fastapi import Query

@app.get("/api/read_column_GoogleTable/")
async def read_columns(columns: list[str] = Query(..., description="Названия колонок через повторение параметра")):
    """
    Чтение указанных колонок из Google таблицы

    Пример использования:

    GET /api/read_column_GoogleTable/?columns=Date&columns=Amount&columns=Description
    """
    specific_columns = await service_GoogleSheet_Ledger.read_specific_columns(columns)
    print(specific_columns)
    return specific_columns


@app.get("/api/read_GoogleTable/")
async def read_all_columns_to_dict():
    """
    Чтение всех колонок из Google таблицы
    """
    all_data = await service_GoogleSheet_Ledger.read_all_columns_to_dict()

    return JSONResponse(
        content=all_data,
        media_type="application/json; charset=utf-8"
    )


@app.get("/api/table-structure")
async def get_table_structure():
    """Получение структуры таблицы (колонок и возможных значений)"""
    try:
        global table_structure
        table_structure = await service_GoogleSheet_Ledger.read_all_columns_to_dict()
        return table_structure
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/add-to-sheet")
async def add_to_sheet(row_data: Dict):
    print("/api/add-to-sheet, row_data", row_data)
    try:
        # 1. Добавление в Ledger
        try:
            # Преобразуем данные для Google Sheets
            sheet_data = {}
            for key, value in row_data.items():

                if isinstance(value, (int, float)):
                    # Числа оставляем как есть - Google Sheets поймет
                    sheet_data[key] = value
                else:
                    # Строки и другие типы
                    sheet_data[key] = str(value) if value is not None else ""

            result = await service_GoogleSheet_Ledger.add_data(sheet_data)
            print("main, /api/add-to-sheet, sheet_data ", sheet_data)
            print(f"✅ Ledger: {result}")

            # 2. Обновление баланса
            try:
                if row_data['Куда'] != '':
                    transaction = {}
                    transaction.setdefault('Валюта', sheet_data['Валюта'])
                    transaction.setdefault('Инстанс', (sheet_data['Куда']))
                    transaction.setdefault('Сумма', sheet_data['Сумма'])
                    balance_updater = await service_GoogleSheet_Balances.update_balance(transaction)
                    print(f"✅ Balance: {balance_updater}")

                if row_data['Откуда'] != '':
                    transaction = {}
                    transaction.setdefault('Валюта', sheet_data['Валюта'])
                    transaction.setdefault('Инстанс', (sheet_data['Откуда']))
                    transaction.setdefault('Сумма', -sheet_data['Сумма'])
                    balance_updater = await service_GoogleSheet_Balances.update_balance(transaction)
                    print(f"✅ Balance: {balance_updater}")
                number_row = result.split()[-1]

                await service_GoogleSheet_Ledger.mark_balance_update(number_row)
            except Exception as e:
                print(f"🟡 Предупреждение Balance: {e}")
                balance_updater = f"Balance update failed: {str(e)}"
            return {
                "status": "success",
                "message": result,
                "balance_update": balance_updater,
                "added_data": row_data
            }

        except Exception as e:
            print(f"🔴 Ошибка Ledger: {e}")
            return {"status": "error", "message": f"Ledger error: {str(e)}"}


    except Exception as e:
        print(f"🔴 Критическая ошибка: {str(e)}")
        return {"status": "error", "message": str(e)}


@app.post("/api/update-sheet")
async def update_balance(data: Dict[str, str]):
    """Обновление баланса"""
    try:
        balance_updater = service_GoogleSheet_Balances.update_balance(data)
        return {
            "status": "success",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from fastapi import FastAPI, HTTPException
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime


@app.get("/api/exchange-rates") # запрос курса валют банк РФ
async def get_exchange_rates():
    """Получение курсов валют от ЦБ РФ"""
    try:
        today = datetime.now().strftime("%d/%m/%Y")
        url = f"http://www.cbr.ru/scripts/XML_daily.asp?date_req={today}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

            # Парсим XML
            root = ET.fromstring(response.text)
            rates = {}

            for valute in root.findall('Valute'):
                char_code = valute.find('CharCode').text
                value = float(valute.find('Value').text.replace(',', '.'))
                nominal = float(valute.find('Nominal').text)
                rates[char_code] = value / nominal
                print(rates[char_code])

            return rates

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения курсов: {str(e)}")


@app.post("/api/send-to-chat")
async def send_to_chat(data_dict: Dict[str, Any]):
    try:
        # Формируем сообщение
        message_text = "✅ 📋 Сообщение от Alex:\n\n"
        for key, value in data_dict.items():
            if type(value) == str and value != "" and "номер строки" not in key.lower(): # не выводим номер строки
                message_text += f"‼️️{value}\n" if "зарплата" in value.lower() else f"` {key}: {value}\n"
            elif type(value) != str and value != "":
                message_text += f"` {key}: {'{:,.2f}'.format(value)}\n"

        # Отправляем в Telegram
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message_text
        )
        # вставлять галочку "✓ чат"
        number_row = int(data_dict['номер строки'])
        await service_GoogleSheet_Ledger.mark_sending_to_chat(number_row)
        return {"success": True, "message": "Данные отправлены в чат"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


