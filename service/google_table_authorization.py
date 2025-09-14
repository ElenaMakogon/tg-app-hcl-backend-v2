from gspread_asyncio import AsyncioGspreadClientManager
from google.oauth2 import service_account
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
import os



load_dotenv(find_dotenv())
BASE_DIR = Path(__file__).parent
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

SAMPLE_SPREADSHEET_ID = os.getenv('sample_spreadsheet_id')



class GoogleSheetsManager:
    def __init__(self):
        self.client_manager = AsyncioGspreadClientManager(
            lambda: self._get_credentials()
        )

    def _get_credentials(self):
        """Получение credentials из переменных окружения"""
        # Проверяем, есть ли переменные окружения
        if all([
            os.getenv('GOOGLE_TYPE'),
            os.getenv('GOOGLE_PRIVATE_KEY'),
            os.getenv('GOOGLE_CLIENT_EMAIL')
        ]):
            # Используем переменные окружения
            return self._get_credentials_from_env()
        else:
            # Fallback: используем файл (для локальной разработки)
            return self._get_credentials_from_file()

    def _get_credentials_from_env(self):
        """Создание credentials из переменных окружения"""
        creds_dict = {
            "type": os.getenv('GOOGLE_TYPE'),
            "project_id": os.getenv('GOOGLE_PROJECT_ID', ''),
            "private_key_id": os.getenv('GOOGLE_PRIVATE_KEY_ID', ''),
            "private_key": os.getenv('GOOGLE_PRIVATE_KEY').replace('\\n', '\n'),
            "client_email": os.getenv('GOOGLE_CLIENT_EMAIL'),
            "client_id": os.getenv('GOOGLE_CLIENT_ID', ''),
            "auth_uri": os.getenv('GOOGLE_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth'),
            "token_uri": os.getenv('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token'),
            "auth_provider_x509_cert_url": os.getenv('GOOGLE_AUTH_PROVIDER_CERT_URL',
                                                     'https://www.googleapis.com/oauth2/v1/certs'),
            "client_x509_cert_url": os.getenv('GOOGLE_CLIENT_CERT_URL', ''),
            "universe_domain": os.getenv('GOOGLE_UNIVERSE_DOMAIN', '')
        }

        return service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )

    def _get_credentials_from_file(self):
        """Резервный метод: чтение из файла (для разработки)"""
        SERVICE_ACCOUNT_FILE = BASE_DIR / 'credentials.json'
        if SERVICE_ACCOUNT_FILE.exists():
            return service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        else:
            raise FileNotFoundError(
                "Credentials not found. Either set environment variables "
                "or place credentials.json in the project directory."
            )
    async def get_client(self):
        return await self.client_manager.authorize()

    async def get_spreadsheet(self):
        client = await self.get_client()
        return await client.open_by_key(SAMPLE_SPREADSHEET_ID)


