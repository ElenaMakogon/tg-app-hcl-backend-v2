from typing import Dict, List, Optional, Union

import sys
import os
# Добавляем корневую директорию проекта в Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from service.google_table_authorization import GoogleSheetsManager
from gspread.utils import a1_to_rowcol, rowcol_to_a1
import gspread
import asyncio

from pydantic import BaseModel, field_validator
from typing import Dict


class SheetRowData(BaseModel):
    # Принимаем и строки и числа
    data: Dict[str, Union[str, int, float]]
    # Валидация для числовых полей
    @field_validator('data')
    @classmethod
    def validate_numeric_fields(cls, data):
        numeric_fields = ['Cумма', 'Эквивалент У.Е', 'USD / RUB']

        for field in numeric_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str):
                    # Преобразуем строку в число если нужно
                    try:
                        # Убираем пробелы и заменяем запятую на точку
                        cleaned_value = value.replace(' ', '').replace(',', '.')
                        data[field] = float(cleaned_value)
                    except (ValueError, AttributeError):
                        # Если не получается преобразовать, оставляем как есть
                        pass
                # Для чисел (int, float) ничего не делаем - оставляем как есть
        print("class SheetRowData(BaseModel) work_with_GoogleTable  data", data)
        return data


class GoogleSheetsService:
    def __init__(self):
        self.manager = GoogleSheetsManager()
        self.sheet_name = 'Ledger'
        self.spreadsheet = None
        self.worksheet = None
        self._headers = []  # Храним заголовки колонок

    async def initialize(self):
        """Инициализация подключения к таблице"""
        if not self.spreadsheet:
            self.spreadsheet = await self.manager.get_spreadsheet()
            self.worksheet = await self.spreadsheet.worksheet(self.sheet_name)
            # Получаем и сохраняем заголовки
            self._headers = await self._get_headers()


    async def _get_headers(self) -> List[str]:
        """Получает заголовки таблицы (первая строка)"""
        try:
            # Получаем первую строку
            header_row = await self.worksheet.row_values(1)
            return header_row
        except Exception as e:
            print(f"Ошибка получения заголовков: {e}")
            return []


    async def add_data(self, data: Dict) -> str:
        """Добавление данных в таблицу"""
        try:
            await self.initialize()  # Убедимся, что подключение установлено

            # Подготовка данных
            row_data = []
            for header in self._headers:
                # Берем значение из данных или пустую строку
                value = data.get(header, "")
                row_data.append(value)

            print("Данные для добавления:", row_data)

            # Находим следующую пустую строку
            next_row = await self._get_next_empty_row()

            # Записываем данные в конкретную строку и колонки
            await self._write_to_specific_row(next_row, row_data)

            return f"✅ Данные успешно добавлены в строку {next_row}"

        except Exception as e:
           return f"❌ Ошибка при работе с Google Таблицей: {str(e)}"


    async def _get_next_empty_row(self) -> int:
        """Находит следующую пустую строку в таблице"""
        try:
            # Получаем все данные
            all_data = await self.worksheet.get_all_values()

            # Ищем первую полностью пустую строку
            for i, row in enumerate(all_data, 1):
                if not any(row):  # Если строка полностью пустая
                    return i

            # Если пустых строк нет, возвращаем следующую после последней
            return len(all_data) + 1

        except Exception as e:
            print(f"Ошибка поиска пустой строки: {e}")
            return 2  # Начинаем со второй строки если заголовок есть

    async def _write_to_specific_row(self, row_number: int, values: List):
        """Записывает данные в конкретную строку"""
        # Формируем диапазон для записи (например, "A2:L2")
        start_col = 'A'
        end_col = chr(64 + len(values))  # Преобразуем количество колонок в букву
        range_name = f"{start_col}{row_number}:{end_col}{row_number}"

        # Записываем данные
        await self.worksheet.update(range_name, [values])


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
            result_where = [] # result для накапливания банков

            # Читаем данные для каждой колонки, беру множество для всплывающих списков фронтбэка
            for i, header in enumerate(self._headers, 1):

                if header:  # Пропускаем пустые заголовки

                    if header.strip() in ['Куда','Откуда']: # формируем один список банков для всплывающих подсказок  во фронте
                        for _ in range(2):
                            column_values = await self.worksheet.col_values(i)
                            result_where.extend([v.strip() for v in column_values[1:] if v])
                        result_where_sort = sorted(list(set(result_where)))
                        result['Куда'] = result_where_sort
                        result['Откуда'] = result_where_sort

                    elif header.strip() in  ['Дата','Сумма','Эквивалент У.Е','USD / RUB']: result[header.strip()] = []

                    else:
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

    async def mark_balance_update(self,row):  # ставим отметку о обновлении баланса
        await self.initialize()
        await self.worksheet.update_acell(f'M{row}', '✓ баланс, web')
        return


    async def mark_sending_to_chat(self,row):  # ставим отметку об отправлении сообщения в чат
        await self.initialize()
        await self.worksheet.update_acell(f'L{row}', '✓ в чат, web')
        return

