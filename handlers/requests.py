from sqlalchemy import select, func
from fastapi.responses import JSONResponse

from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_serializer

from models.models import async_session, UserAuth, UserWallet, UserReport


class WalletSchema(BaseModel):
    id: int
    full_name: str
    token: str
    quantity: float
    resalt_of_quantity: float
    price_of_token: float
    resalt: float
    created_at: datetime
    user_id: int

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()  # Преобразуем datetime в строку


class ReportSchema(BaseModel):
    id: int
    full_name: str
    token: str
    result_of_amount: float
    price_of_token_current: float
    result: float
    updated_at: datetime
    user_id: int

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('updated_at')
    def serialize_up_dt(self, dt: datetime) -> str:
        return dt.isoformat()  # Преобразуем datetime в строку


class DailyReportSchema(BaseModel):
    total_result: float
    date: str

    model_config = ConfigDict(from_attributes=True)


async def get_user(tg_id):  # эту проверку вызывать еще в телеграм, а возможно дальше сделать вход по паролю. если id нет ,
    # то предлагать зарегестрироваться , выдавать форму регистрации
    async with async_session() as session:
        user = await session.scalar(
            select(UserAuth).where(UserAuth.id_telegram == str(tg_id)))
        user_id = user.id
        user_fullname = user.full_name
        if user:
            return user_id
        else:
            return print("форма регистрации, добавить нового юзера")


async def get_wallet_user(user_id):  # получение портфеля пользователя
    async with async_session() as session:
        subq = (select(UserWallet.token, func.max(UserWallet.created_at).label("max_created_at"))
                .where(UserWallet.user_id == user_id)
                .group_by(UserWallet.token)
                .subquery())

        wallet_out = await session.execute(
            select(UserWallet)
            .join(subq, (UserWallet.token == subq.c.token) &
                  (UserWallet.created_at == subq.c.max_created_at))
            .where(UserWallet.user_id == user_id)
            .order_by(UserWallet.token)
        )

        wallet = wallet_out.scalars().all()

        # Сериализация через Pydantic
        serialized = [WalletSchema.model_validate(t).model_dump() for t in wallet]

        # Возвращаем с явным указанием кодировки
        return JSONResponse(
            content=serialized,
            media_type="application/json; charset=utf-8"
        )


async def get_report_user(user_id):  # получение отчета пользователя
    async with async_session() as session:
        result = await session.execute(
            select(UserReport)
            .where(UserReport.user_id == user_id)
            .order_by(UserReport.updated_at))

        user_report = result.scalars().all()
        if user_report:
            date_full_name = user_report[0].full_name
            # Создаем словарь для группировки по дням
            daily_results = {}
            for item in user_report:
                # Обращаемся к атрибутам объекта через точку
                date_str = item.updated_at.isoformat().split("T")[0]
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                # Добавляем результат в соответствующую дату
                if date_obj in daily_results:
                    daily_results[date_obj] += item.result
                else:
                    daily_results[date_obj] = item.result

            # Формируем итоговый список
            result_list = [{"date": str(date), "total_result": total} for date, total in daily_results.items()]
            # Сортируем по дате
            result_list.sort(key=lambda x: x["date"])
            #result_list += [date_full_name]

            # Сериализация через Pydantic
            serialized = [DailyReportSchema.model_validate(r).model_dump() for r in result_list]

            # Возвращаем с явным указанием кодировки
            return JSONResponse(
                content=serialized,
                media_type="application/json; charset=utf-8"
            )