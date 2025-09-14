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
        "http://localhost:5173",# Для разработки
        "http://127.0.0.1:8000",# Для разработки
        "http://www.cbr.ru"
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


# Запуск бота Lora, является админом в группе "ОТЛ_ЧАТ_КНОПКИ" TELEGRAM_CHAT_ID =-1002812481370(в отдельном потоке)
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling())


# Глобальная переменная для хранения структуры таблицы
table_structure = {}

@app.get("/")
async def root():
    return {"message": "Привет"}


@app.get("/api/wallet/{tg_id}") # первая страница, отображает портфель покупки
async def user_wallet(tg_id: str):
    user_id = await rq.get_user(tg_id)
    wallet = await rq.get_wallet_user(user_id)
    return wallet

@app.get("/api/wallet_update/{tg_id}") # страница, отображает обнлвленный портфель
async def user_wallet(tg_id: str):
    user_id = await rq.get_user(tg_id)
    wallet = await rq.get_wallet_user(user_id)
    return wallet

@app.get("/api/report/{tg_id}") # страница, отображает отчет: дата--total, а также почта--OK прислать отчет на почеу
async def user_report(tg_id: str):
    user_id = await rq.get_user(tg_id)
    report = await rq.get_report_user(user_id)
    return report


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
        # Здесь ваш код для чтения из Google Sheets
        # Возвращаем структуру в формате:
        # {"Валюта": ["ETH", "BTC"], "Банк": ["Банк1", "Банк2"]}
        global table_structure
        table_structure = await service_GoogleSheet_Ledger.read_all_columns_to_dict()
        return table_structure
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/add-to-sheet")
async def add_to_sheet(row_data: Dict[str, str]):
    try:
        # 1. Добавление в Ledger
        try:
            result = await service_GoogleSheet_Ledger.add_data(row_data)
            print(f"✅ Ledger: {result}")
        except Exception as e:
            print(f"🔴 Ошибка Ledger: {e}")
            return {"status": "error", "message": f"Ledger error: {str(e)}"}


        # 2. Обновление баланса
        try:

            if row_data['Куда'] != '':
                transaction = {}
                transaction.setdefault('Валюта', row_data['Валюта'])
                transaction.setdefault('Инстанс', (row_data['Куда']))
                transaction.setdefault('Сумма', row_data['Сумма'])
                balance_updater = await service_GoogleSheet_Balances.update_balance(transaction)
                print(f"✅ Balance: {balance_updater}")

            if row_data['Откуда'] != '':
                transaction = {}
                transaction.setdefault('Валюта', row_data['Валюта'])
                transaction.setdefault('Инстанс', (row_data['Откуда']))
                transaction.setdefault('Сумма', '-'+row_data['Сумма'])
                balance_updater = await service_GoogleSheet_Balances.update_balance(transaction)
                print(f"✅ Balance: {balance_updater}")
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


def validate_row_data(row_data: Dict[str, str], table_structure: Dict[str, List[str]]) -> List[str]:
    """Валидация данных строки"""
    errors = []

    # Проверяем, что все обязательные поля присутствуют
    for column in table_structure.keys():
        if column not in row_data or not row_data[column].strip():
            errors.append(f"Поле '{column}' обязательно для заполнения")

    # Проверяем, что значения соответствуют ожидаемым (если есть варианты)
    for column, value in row_data.items():
        if column in table_structure and table_structure[column]:
            expected_values = table_structure[column]
            if value not in expected_values:
                errors.append(
                    f"Значение '{value}' недопустимо для поля '{column}'. Допустимые значения: {', '.join(expected_values)}")

    return errors
# # Вариант с query parameters (рекомендуется)
# #curl "http://localhost:8000/api/read_column_GoogleTable/?columns=Date&columns=Amount&columns=Description

from fastapi import FastAPI, HTTPException
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime


@app.get("/api/exchange-rates")
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


# Модели Pydantic
class FormData(BaseModel):
    name: str
    age: str
    # другие поля

@app.post("/api/send-to-chat")
async def send_to_chat(data_dict: Dict[str, Any]):
    try:
        print(f"получаемый от фронта  {data_dict} ")
        # Формируем сообщение
        message_text = "✅ 📋 Сообщение от Alex:\n\n"
        for key, value in data_dict.items():
            if value != "":
                message_text += f"‼️️{value}\n" if "зарплата" in value.lower() else f"` {key}: {value}\n"

        # Отправляем в Telegram
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message_text
        )

        return {"success": True, "message": "Данные отправлены в чат"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")





