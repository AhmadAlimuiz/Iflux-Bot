import os
import time
import requests
import threading
import random
import configparser
import logging
from dotenv import load_dotenv

# --- SETUP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)

# --- LOAD CONFIGURATION ---
def load_config():
    """Memuat konfigurasi dari file config.ini."""
    config = configparser.ConfigParser()
    if not os.path.exists('config.ini'):
        logging.error("File config.ini tidak ditemukan!")
        exit()
    config.read('config.ini')
    return config['settings']

CONFIG = load_config()
API_BASE_URL = CONFIG.get('api_base_url')
BASE_HEARTBEAT_INTERVAL = CONFIG.getint('base_heartbeat_interval')
JITTER_MIN = CONFIG.getint('jitter_min_percent') / 100.0
JITTER_MAX = CONFIG.getint('jitter_max_percent') / 100.0
MAX_RETRY_DELAY = CONFIG.getint('max_retry_delay')
START_DELAY_MIN = CONFIG.getint('start_delay_min')
START_DELAY_MAX = CONFIG.getint('start_delay_max')

# --- LOAD SENSITIVE DATA ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- FILE PATHS ---
ACCOUNTS_FILE = "accounts.txt"
TOKENS_FILE = "tokens.txt"

# --- USER-AGENT ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# --- HELPER FUNCTIONS ---
def send_telegram_message(message):
    """Mengirim pesan notifikasi ke Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.exceptions.RequestException:
        logging.error("Gagal mengirim notifikasi Telegram.")

def load_tokens():
    """Memuat token dari file."""
    tokens = {}
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            for line in f:
                email, token = line.strip().split(':', 1)
                tokens[email] = token
    return tokens

def save_token(email, token):
    """Menyimpan token baru ke file."""
    tokens = load_tokens()
    tokens[email] = token
    with open(TOKENS_FILE, 'w') as f:
        for e, t in tokens.items():
            f.write(f"{e}:{t}\n")
    logging.info(f"Token untuk {email} telah disimpan.")

# --- CORE LOGIC ---
def get_bearer_token(email, password):
    """Login untuk mendapatkan token baru."""
    url = f"{API_BASE_URL}/api/auth/login"
    payload = {"email": email, "password": password}
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/json',
        'Origin': 'https://depin.iflux.global',
        'Referer': 'https://depin.iflux.global/auth/login',
        'User-Agent': USER_AGENT
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("status") and "token" in data.get("data", {}):
            logging.info(f"[{email}] Login berhasil.")
            return data["data"]["token"]
        else:
            logging.error(f"[{email}] Login gagal: {data.get('message', 'Respons tidak valid')}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"[{email}] Error saat login: {e}")
        return None

def get_or_refresh_token(email, password):
    """Mendapatkan token dari file atau login ulang jika perlu."""
    tokens = load_tokens()
    if email in tokens:
        logging.info(f"[{email}] Menggunakan token yang tersimpan.")
        return tokens[email]
    else:
        logging.info(f"[{email}] Token tidak ditemukan, mencoba login...")
        token = get_bearer_token(email, password)
        if token:
            save_token(email, token)
        return token

def run_node_simulation(email, password):
    """Menjalankan simulasi node untuk satu akun."""
    logging.info(f"[{email}] Memulai thread simulasi node.")
    
    token = get_or_refresh_token(email, password)
    if not token:
        logging.error(f"[{email}] Gagal mendapatkan token. Thread dihentikan.")
        return

    status_url = f"{API_BASE_URL}/api/user/status"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Authorization': f'Bearer {token}',
        'Origin': 'https://depin.iflux.global',
        'Referer': 'https://depin.iflux.global/',
        'User-Agent': USER_AGENT
    }
    
    retry_delay = 60

    while True:
        try:
            logging.info(f"[{email}] Mengecek status...")
            response = requests.get(status_url, headers=headers, timeout=15)
            retry_delay = 60 # Reset delay jika berhasil

            if response.status_code == 200:
                data = response.json()
                if data.get("status"):
                    points = data.get("data", {}).get("points", "N/A")
                    logging.info(f"[{email}] Status OK. Total poin: {points}")
                else:
                    logging.warning(f"[{email}] Cek status gagal: {data.get('message')}")
            elif response.status_code == 401: # Unauthorized, token mungkin kadaluarsa
                logging.warning(f"[{email}] Token tidak valid. Mencoba login ulang...")
                token = get_bearer_token(email, password)
                if token:
                    save_token(email, token)
                    headers['Authorization'] = f'Bearer {token}'
                else:
                    logging.error(f"[{email}] Gagal refresh token. Menunggu 10 menit.")
                    time.sleep(600)
                    continue
            else:
                logging.warning(f"[{email}] Error cek status. Status: {response.status_code}")

            # Jitter
            jitter_factor = random.uniform(JITTER_MIN, JITTER_MAX)
            actual_delay = BASE_HEARTBEAT_INTERVAL * jitter_factor
            logging.info(f"[{email}] Menunggu {actual_delay:.0f} detik...")
            time.sleep(actual_delay)

        except requests.exceptions.RequestException as e:
            logging.error(f"[{email}] Koneksi error: {e}. Mencoba lagi dalam {retry_delay} detik.")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)

def main():
    """Fungsi utama untuk menjalankan semua akun."""
    logging.info("--- Memulai iFlux Bot (Versi Profesional) ---")
    
    if not os.path.exists(ACCOUNTS_FILE):
        logging.error(f"File '{ACCOUNTS_FILE}' tidak ditemukan.")
        return

    with open(ACCOUNTS_FILE, 'r') as f:
        accounts = [line.strip() for line in f if line.strip()]

    if not accounts:
        logging.error(f"File '{ACCOUNTS_FILE}' kosong.")
        return

    threads = []
    for i, account_line in enumerate(accounts):
        try:
            email, password = account_line.split(':', 1)
            email = email.strip()
            password = password.strip()
            
            thread = threading.Thread(target=run_node_simulation, args=(email, password), name=f"Node-{email[:10]}")
            thread.daemon = True
            threads.append(thread)
            thread.start()
            
            delay = random.randint(START_DELAY_MIN, START_DELAY_MAX)
            logging.info(f"Menunggu {delay} detik sebelum memulai akun berikutnya...")
            time.sleep(delay)

        except ValueError:
            logging.error(f"Format akun tidak valid: '{account_line}'. Gunakan format 'email:password'.")
            continue
    
    if not threads:
        logging.error("Tidak ada node yang berhasil dimulai. Program berhenti.")
        return

    logging.info(f"--- {len(threads)} node simulasi sedang berjalan. Tekan Ctrl+C untuk berhenti. ---")
    send_telegram_message("🚀 iFlux Bot telah dimulai.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("--- Program dihentikan oleh pengguna. ---")
        send_telegram_message("🛑 iFlux Bot telah dihentikan.")

if __name__ == "__main__":
    main()
