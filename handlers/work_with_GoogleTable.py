from typing import Dict, List, Optional
from service.google_table_authorization import GoogleSheetsManager
from gspread.utils import a1_to_rowcol, rowcol_to_a1
import gspread
import asyncio

from pydantic import BaseModel
from typing import Dict

class SheetRowData(BaseModel):
    # Динамическая модель, которая принимает любые поля
    # но проверяет их на соответствие ожидаемым колонкам
    data: Dict[str, str]


class GoogleSheetsService:
    def __init__(self):
        self.manager = GoogleSheetsManager()
        self.sheet_name = 'Ledger'
        self.spreadsheet = None
        self.worksheet = None

    async def initialize(self):
        """Инициализация подключения к таблице"""
        if not self.spreadsheet:
            self.spreadsheet = await self.manager.get_spreadsheet()
            self.worksheet = await self.spreadsheet.worksheet(self.sheet_name)
            # Получаем заголовки при инициализации
            self._headers = await self._get_headers()


    async def add_data(self, data: Dict) -> str:
        """Добавление данных в таблицу"""
        try:
            await self.initialize()  # Убедимся, что подключение установлено

            # Подготовка данных
            row = [str(value) for value in data.values()]

            # Асинхронное добавление строки
            await self.worksheet.append_row(row)  ########  добавить форматирование

            return "✅ Данные успешно добавлены в 'Ledger'"

        except Exception as e:
            return f"❌ Ошибка при работе с Google Таблицей: {str(e)}"


    async def _get_headers(self) -> List[str]:
        """Получение заголовков таблицы (первая строка)"""
        try:
            headers = await self.worksheet.row_values(1)
            return headers if headers else []
        except Exception:
            return []


    async def read_column(self, column_letter: str) -> List[str]:
        """
        Чтение данных из указанной колонки (по букве: 'A', 'B', 'C')

        :param column_letter: Буква колонки ('A', 'B', 'C', ...)
        :return: Список значений колонки (без заголовка)
        """
        try:
            await self.initialize()

            # Получаем все значения колонки
            column_data = await self.worksheet.col_values(
                gspread.utils.column_letter_to_number(column_letter)
            )

            # Возвращаем данные без заголовка (если он есть)
            return column_data[1:] if column_data and len(column_data) > 1 else []

        except Exception as e:
            print(f"Ошибка чтения колонки {column_letter}: {str(e)}")
            return []


    async def read_column_by_index(self, column_index: int) -> List[str]:
        """
        Чтение данных из колонки по индексу (начиная с 1)

        :param column_index: Номер колонки (1, 2, 3, ...)
        :return: Список значений колонки
        """
        return await self.read_column(
            gspread.utils.rowcol_to_a1(1, column_index)[0]  # Преобразуем индекс в букву
        )


    async def read_all_columns_to_dict(self) -> Dict[str, List[str]]:
        """
        Чтение всех колонок и преобразование в словарь

        :return: Словарь {название_колонки: [значения]}
        """
        try:
            await self.initialize()

            if not self._headers:
                self._headers = await self._get_headers()

            if not self._headers:
                return {}

            result = {}

            # Читаем данные для каждой колонки, беру множество для всплывающих списков фронтбэка
            for i, header in enumerate(self._headers, 1):

                if header:  # Пропускаем пустые заголовки
                    column_values = await self.worksheet.col_values(i)
                    # Сохраняем значения без заголовка
                    result[header.strip()] = sorted(list(set([v.strip() for v in column_values[1:] if v]))) if len(column_values) > 1 else []

            return result

        except Exception as e:
            print(f"Ошибка чтения всех колонок: {str(e)}")
            return {}


    async def read_specific_columns(self, column_names: List[str]) -> Dict[str, List[str]]:
        """
        Чтение только указанных колонок

        :param column_names: Список названий колонок для чтения
        :return: Словарь {название_колонки: [значения]}
        """
        try:
            await self.initialize()

            if not self._headers:
                self._headers = await self._get_headers()

            result = {}

            for col_name in column_names:
                if col_name in self._headers:
                    col_index = self._headers.index(col_name) + 1
                    column_values = await self.worksheet.col_values(col_index)
                    result[col_name] = column_values[1:] if len(column_values) > 1 else [] # во фронте брать множество от значений
                else:
                    result[col_name] = []  # Колонка не найдена

            return result

        except Exception as e:
            print(f"Ошибка чтения указанных колонок: {str(e)}")
            return {}


    async def get_column_with_headers(self, column_letter: str) -> Dict[str, List[str]]:
        """
        Чтение колонки с сохранением заголовка как ключа

        :param column_letter: Буква колонки ('A', 'B', 'C')
        :return: Словарь {заголовок: [значения]}
        """
        try:
            await self.initialize()

            if not self._headers:
                self._headers = await self._get_headers()

            col_index = gspread.utils.column_letter_to_number(column_letter)

            if col_index <= len(self._headers):
                header = self._headers[col_index - 1]
                values = await self.worksheet.col_values(col_index)

                return {
                    header: values[1:] if len(values) > 1 else []
                }
            else:
                return {}

        except Exception as e:
            print(f"Ошибка чтения колонки с заголовком: {str(e)}")
            return {}


"""
# Инициализация сервиса
service = GoogleSheetsService()

# 1. Чтение всех колонок в словарь
all_data = await service.read_all_columns_to_dict()
print(all_data)
# {'Date': ['2024-01-01', '2024-01-02'], 'Amount': ['100', '200'], 'Description': ['Payment', 'Transfer']}

# 2. Чтение конкретных колонок
specific_columns = await service.read_specific_columns(['Date', 'Amount'])
print(specific_columns)
# {'Date': ['2024-01-01', '2024-01-02'], 'Amount': ['100', '200']}

# 3. Чтение колонки по букве
column_a = await service.read_column('A')
print(column_a)
# ['2024-01-01', '2024-01-02']

# 4. Чтение колонки с заголовком
column_with_header = await service.get_column_with_headers('B')
print(column_with_header)
# {'Amount': ['100', '200']}

# Пример использования в aiogram хендлере
async def async_add_to_google_sheet(data: dict) -> str:
    #Обертка для совместимости с вашим текущим кодом
    service = GoogleSheetsService()
    return await service.add_data(data)
"""
