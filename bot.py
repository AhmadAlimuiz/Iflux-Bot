import os
import time
import requests
import threading
import random
import json

# --- KONFIGURASI ---
# Ubah nilai-nilai ini sesuai kebutuhan Anda
API_BASE_URL = "https://api.iflux.global"
BASE_HEARTBEAT_INTERVAL = 300  # Interval dasar dalam detik (contoh: 300 detik = 5 menit)
JITTER_MIN_PERCENT = 80        # Jeda minimum (80% dari interval dasar)
JITTER_MAX_PERCENT = 120       # Jeda maksimum (120% dari interval dasar)
MAX_RETRY_DELAY = 900          # Maksimal penundaan saat error (dalam detik)
START_DELAY_MIN = 10           # Jeda minimum antar start akun
START_DELAY_MAX = 30           # Jeda maksimum antar start akun

# --- NOTIFIKASI TELEGRAM (OPSIONAL) ---
# Isi dengan token dan chat ID Anda jika ingin notifikasi. Jika tidak, biarkan kosong.
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# --- FILE PATHS ---
TOKENS_FILE = "tokens.json"
PROXY_FILE = "proxy.txt"

# --- USER-AGENT ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# --- FUNGSI HELPER ---
def send_telegram_message(message):
    """Mengirim pesan notifikasi ke Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.exceptions.RequestException:
        print("ERROR: Gagal mengirim notifikasi Telegram.")

def load_accounts():
    """Memuat data akun dari tokens.json."""
    if not os.path.exists(TOKENS_FILE):
        print(f"ERROR: File '{TOKENS_FILE}' tidak ditemukan!")
        return None
    try:
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"ERROR: File '{TOKENS_FILE}' tidak valid atau rusak.")
        return None

# --- LOGIKA UTAMA BOT ---
def run_node_simulation(account):
    """Menjalankan simulasi node untuk satu akun."""
    email = account['email']
    token = account['token']
    proxy = account.get('proxy') # Ambil proxy jika ada, jika tidak akan None
    
    print(f"[{email}] 🚀 Memulai thread simulasi node...")

    status_url = f"{API_BASE_URL}/api/user/status"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Authorization': token,
        'Origin': 'https://depin.iflux.global',
        'Referer': 'https://depin.iflux.global/',
        'User-Agent': USER_AGENT
    }
    
    # Siapkan proxy
    proxies = None
    if proxy:
        proxies = {
            'http': proxy,
            'https': proxy
        }
        print(f"[{email}] 🔌 Menggunakan proxy: {proxy}")
    else:
        print(f"[{email}] 🌐 Berjalan tanpa proxy.")

    retry_delay = 60

    while True:
        try:
            print(f"[{email}] 💓 Mengecek status...")
            response = requests.get(status_url, headers=headers, proxies=proxies, timeout=15)
            retry_delay = 60 # Reset delay jika berhasil

            if response.status_code == 200:
                data = response.json()
                if data.get("status"):
                    points = data.get("data", {}).get("points", "N/A")
                    print(f"[{email}] ✅ Status OK. Total poin: {points}")
                else:
                    print(f"[{email}] ⚠️ Cek status gagal: {data.get('message')}")
            elif response.status_code == 401:
                print(f"[{email}] ❌ ERROR: Token tidak valid atau kadaluarsa. Thread dihentikan. Silakan perbarui token di {TOKENS_FILE}.")
                send_telegram_message(f"❌ Token untuk {email} kadaluarsa. Bot perlu diperbarui.")
                return # Hentikan thread ini
            else:
                print(f"[{email}] ❌ Error cek status. Status: {response.status_code}")

            # Jitter
            jitter_factor = random.uniform(JITTER_MIN_PERCENT / 100.0, JITTER_MAX_PERCENT / 100.0)
            actual_delay = BASE_HEARTBEAT_INTERVAL * jitter_factor
            print(f"[{email}] ⏳ Menunggu {actual_delay:.0f} detik...")
            time.sleep(actual_delay)

        except requests.exceptions.RequestException as e:
            print(f"[{email}] ❌ Koneksi error: {e}. Mencoba lagi dalam {retry_delay} detik.")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)

def main():
    """Fungsi utama untuk menjalankan semua akun."""
    print("--- Memulai iFlux Bot (Versi Minimalis) ---")
    
    accounts = load_accounts()
    if not accounts:
        print("Tidak ada akun yang dimuat. Program berhenti.")
        return

    threads = []
    for account in accounts:
        # Validasi data akun
        if 'email' not in account or 'token' not in account:
            print(f"WARNING: Melewati data akun tidak valid: {account}")
            continue
            
        thread = threading.Thread(target=run_node_simulation, args=(account,), name=f"Node-{account['email'][:10]}")
        thread.daemon = True
        threads.append(thread)
        thread.start()
        
        delay = random.randint(START_DELAY_MIN, START_DELAY_MAX)
        print(f"Menunggu {delay} detik sebelum memulai akun berikutnya...")
        time.sleep(delay)
    
    if not threads:
        print("Tidak ada node yang berhasil dimulai. Program berhenti.")
        return

    print(f"--- {len(threads)} node simulasi sedang berjalan. Tekan Ctrl+C untuk berhenti. ---")
    send_telegram_message("🚀 iFlux Bot (Versi Minimalis) telah dimulai.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n--- Program dihentikan oleh pengguna. ---")
        send_telegram_message("🛑 iFlux Bot telah dihentikan.")

if __name__ == "__main__":
    main()
