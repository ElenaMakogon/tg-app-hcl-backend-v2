import os

from datetime import datetime

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncAttrs

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

engine = create_async_engine(os.getenv("DATABASE_URL"), echo=True)
async_session = async_sessionmaker(
            engine,
            expire_on_commit=False
        )



class Base(AsyncAttrs, DeclarativeBase):
    pass
# права доступа в dbeaver пользователю
#GRANT ALL PRIVILEGES ON DATABASE hcl TO elenamakogon;
#GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO elenamakogon;


class UserAuth(Base):
    __tablename__ = 'users_auth'
    __table_args__ = {'schema': 'public'}  # Явно указываем схему public

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name  = Column(String(50))
    id_telegram = Column(String(20),default='')
    login = Column(String(50))
    password = Column(String(250))
    date = Column(DateTime,  default=datetime.utcnow)
    mail = Column(String(100))

    wallets = relationship('UserWallet', back_populates='user')
    reports = relationship('UserReport', back_populates='user_report')



class UserWallet(Base):
    __tablename__ = 'users_wallets'
    __table_args__ = {'schema': 'public'}  # Явно указываем схему public

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    token = Column(String(255), nullable=False)
    quantity = Column(Numeric, nullable=False)
    resalt_of_quantity = Column(Numeric, nullable=False)
    price_of_token = Column(Numeric, nullable=False)
    resalt = Column(Numeric, nullable=False)
    created_at = Column(DateTime,  default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey('public.users_auth.id'), nullable=False)

    # Связь с пользователем (если нужно)
    user = relationship('UserAuth', back_populates='wallets')


class UserReport(Base):
    __tablename__ = 'users_reports'
    __table_args__ = {'schema': 'public'}  # Явно указываем схему public

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    token = Column(String(255), nullable=False)
    result_of_amount = Column(Numeric, nullable=False)
    price_of_token_current = Column(Numeric, nullable=False)
    result = Column(Numeric, nullable=False)
    updated_at = Column(DateTime,  default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey('public.users_auth.id'), nullable=False)

    # Связь с пользователем (если нужно)
    user_report = relationship('UserAuth', back_populates='reports')


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all) #.metadata.create_all