from service.google_table_authorization import GoogleSheetsManager

from typing import Dict, Optional
from gspread.utils import a1_to_rowcol, rowcol_to_a1


class GoogleSheetsBalanceUpdater:
    def __init__(self):
        self.manager = GoogleSheetsManager()
        self.sheet_name = 'Balances'
        self.spreadsheet = None
        self.worksheet = None

    async def initialize(self):
        """Инициализация подключения к таблице"""
        if not self.spreadsheet:
            self.spreadsheet = await self.manager.get_spreadsheet()
            self.worksheet = await self.spreadsheet.worksheet(self.sheet_name)
            await self._detect_table_structure()

    async def _detect_table_structure(self):
        """Определение структуры таблицы"""
        # Находим заголовок "Инстанс" (может быть с опечаткой)
        header = "Инстанс"

        try:
            cell = await self.worksheet.find(header)
            self.instance_col = rowcol_to_a1(1, cell.col)[0]  # Буква колонки
            print(f"Буква колонки {self.instance_col}")
            self.instance_header_row = cell.row
            self.instance_header_col= cell.col # Цифра колонки для вставки новой валюты колонки
        except Exception:
            print("Не удалось найти заголовок с инстансами")
        # Строка с валютами (на 1 строку ниже)
        self.currency_header_row = self.instance_header_row + 1

        # Первая строка с данными (еще на 1 строку ниже)
        self.first_data_row = self.currency_header_row + 1 # берем для вставки нового инстанс после второй строки данных,
        # для сохранения сущестующего форматирования ячеек

        # Находим строку "Всего"
        try:
            total_cell = await self.worksheet.find("Всего")
            self.total_row = total_cell.row
        except Exception:
            self.total_row = None


    async def update_balance(self, transaction: Dict) -> str:
        """Обновляет баланс в таблице"""

        await self.initialize()
        print(f"******** работает update_balance. transaction = {transaction}")
        # Получаем список валют
        currencies = await self.worksheet.row_values(self.currency_header_row)

        if currencies and (transaction['Валюта'] not in currencies):
            currency_name = transaction['Валюта'].strip()
            # Добавляем новую колонку после 'Инстанс'
            await self._add_new_column_currency(currency_name)
        try:
            # Находим колонку для валюты
            currencies = await self.worksheet.row_values(self.currency_header_row)
            currency_col = rowcol_to_a1(1, currencies.index(transaction['Валюта']) + 1)[0]
            print(f"колонка для валюты {(transaction['Валюта'])} - {currency_col}")

            # Проверяем существование инстанса
            instance_row = await self._find_instance_row(transaction['Инстанс'])

            if instance_row is None:
                # Добавляем новый инстанс перед старыми
                 await self._add_new_instance(transaction, currency_col)

                # Обновляем существующий балан
            instance_row = await self._find_instance_row(transaction['Инстанс'])
            return await self._update_existing_balance(
                transaction,
                instance_row,
                currency_col
            )

        except Exception as e:
            return f"❌ Ошибка при обновлении баланса: {str(e)}"


    async def _find_instance_row(self, instance_name: str) -> Optional[int]:
        """Находит строку с указанным инстансом"""
        instances = await self.worksheet.col_values(a1_to_rowcol(f'{self.instance_col}1')[1])
        for i, value in enumerate(instances, 1):
            if value == instance_name:
                return i
        return None


    async def _add_new_instance(self, transaction: dict, currency_col: str) -> str:
        """Добавляет новый инстанс перед существующими записями"""
        # Определяем позицию для вставки (после заголовков и перед старыми данными)
        insert_row = self.first_data_row

        # Подготавливаем новую строку
        currencies = await self.worksheet.row_values(self.currency_header_row)
        new_row = [""] * len(currencies)
        new_row[1] = transaction['Инстанс']  # В колонке инстансов

        # Вставляем новую строку
        await self.worksheet.insert_row(
            values=new_row,
            index=insert_row
        )

        # Обновляем позицию "Всего", если она была

        total_cell = await self.worksheet.find("Всего")
        self.total_row = total_cell.row
        print(f"self.total_row = {self.total_row}")

        return f"✅ Добавлен новый инстанс '{transaction['Инстанс']}' с суммой {transaction['Сумма']} {transaction['Валюта']}"


    async def _add_new_column_currency(self,  currency: str) -> str:
        """Добавляет новую валюту после колонки 'Инстанс'"""
        # Определяем позицию для вставки (после первой валюты для сохранения форматированияи )
        try:
            insert_col = self.instance_header_col + 2

            # Вставляем новую колонку

            await self.worksheet.insert_cols([[]], insert_col, value_input_option='USER_ENTERED') # self.insert_col
            # Устанавливаем заголовок во второй строке
            await self.worksheet.update('D3', [[currency]])  # C - третья колонка
            column_range = f"{'D'}:{'D'}" # устанавливаем пользовательский формат для всей колонки, иначе устанавливает
            # таблица, без разделения на тысячи

            # Устанавливаем кастомный числовой формат
            await self.worksheet.format(column_range, {
                "numberFormat": {
                    "type": "NUMBER",
                    "pattern": "#,##0.00"  # Кастомный формат с пробелами
                }
            })

            return print(f"✅ Добавлена новая колонка валюты  {currency} ")
        except Exception as e:
            return f"❌ Ошибка добавления колонки: {str(e)}"



    async def _reFormatting(self, num: str): ## применяем при ЗАПИСИ строкового
        # представления числа для единого вида форматирования: "-35 000,00". Для арифметических операций требует брать
        # float(numStr.replace(" ","").replace(",","."))
        import re

        if type(num) == str and type(num) != None:
            num_clear = re.sub(r"[^0-9-+.,]", "", num)
            if ("," and ".") in num_clear:
                num_clear = num_clear.replace(",", "")

            else:

                num_clear = num_clear.replace(",", ".")
        else:
            return "0"
        return num_clear


    async def _update_existing_balance(
            self,
            transaction: dict,
            row_num: int,
            currency_col: str
    ) -> str:
        """Обновляет баланс существующего инстанса"""
        cell_ref = f'{currency_col}{row_num}'
        cell = await self.worksheet.acell(cell_ref)
        current_value = await self._reFormatting(cell.value.strip() if cell.value else "0")

        current_num = float(current_value)

        #current_num = float(current_value)
        sum_num = transaction['Сумма']

        #sum_num = float(sum_value)
        new_value = current_num + sum_num

        print(f"*********  работает  _update_existing_balance , current_num = {current_num}, sum_num = {sum_num}, new_value = {new_value}")
        #formatted_new_value = "{:,.2f}".format(new_value).replace(","," ").replace(".",",")

        await self.worksheet.update_acell(cell_ref, new_value)

        # Обновляем итоги
        await self._update_totals(currency_col)

        return f"✅ Обновлен баланс 'Balances'\n {transaction['Инстанс']}: {current_num} → {new_value} {transaction['Валюта']}"


    async def _update_totals(self, currency_col: str) -> str:
        """Пересчитывает итоги по указанной валюте"""
        if not self.total_row:
            return "❌ Строка 'Всего' не найдена"
        print(f"_update_totals self.total_row={self.total_row}, currency_col={currency_col}")
        values = await self.worksheet.col_values(a1_to_rowcol(f'{currency_col}1')[1])
        print(f"values = {values}")
        total = 0.0

        for i, value in enumerate(values, 1):
            if i != self.total_row and i >= self.first_data_row:
                try:
                    cleaned_value = await self._reFormatting(value.strip())  #re.sub(r'[^0-9-]', '', value) if value else '0'
                    total += float(cleaned_value)
                    print(f"value = {value}, cleaned_value = {cleaned_value}, total = {total}")
                except ValueError:
                    continue

        formatted_total = "{:,.2f}".format(total).replace(","," ").replace(".",",")
        print(f'итого в: {currency_col}{self.total_row} , значение: {formatted_total}')
        await self.worksheet.update_acell(f'{currency_col}{self.total_row}', formatted_total)
        return print("✅ Итоги обновлены")




