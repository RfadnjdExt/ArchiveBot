# ArchiveBot

<p align="center">
  <img src="https://cdn.lewd.host/mvgITeV1.png" alt="ArchiveBot Logo" width="150"/>
</p>

Sebuah bot Discord yang dirancang untuk mengekspor riwayat percakapan dari satu channel ke channel lain secara bersih dan terstruktur. Bot ini bukan sekadar _forwarder_, melainkan sebuah alat arsip yang cerdas, mengelompokkan pesan, mempertahankan identitas pengirim, dan menangani lampiran dengan baik.

---

## ✨ Fitur Utama

- **Pengelompokan Pesan Cerdas**: Pesan berurutan dari pengguna yang sama dalam rentang waktu tertentu digabungkan menjadi satu kiriman untuk mengurangi kebisingan dan meningkatkan keterbacaan.
- **Impersonasi dengan Webhook**: Menggunakan webhook untuk mengirim pesan di channel target, sehingga nama dan avatar pengguna asli tetap ditampilkan, membuat arsip terasa otentik.
- **Penyimpanan Progres**: Secara otomatis menyimpan ID pesan terakhir yang diproses. Jika bot dihentikan dan dijalankan kembali, proses akan dilanjutkan dari titik terakhir, mencegah duplikasi data.
- **Penanganan Lampiran Lanjutan**:
  - File di bawah 10 MB akan diunduh dan diunggah kembali secara langsung.
  - File besar (> 10 MB) diunggah ke host eksternal ([lewd.host](https://lewd.host/)) dan link-nya akan dibagikan, mengatasi batasan ukuran file Discord.
- **Format Pesan Rapi**:
  - Pesan yang sangat panjang akan dipecah menjadi beberapa bagian tanpa memotong kalimat di tengah.
  - Setiap grup pesan diberi stempel waktu relatif (misal: "beberapa saat lalu") untuk konteks.
- **Tangguh dan Andal**: Dilengkapi logika _retry_ dengan _backoff_ untuk menangani _rate limit_ dari API Discord (HTTP 429/503) secara otomatis.

## ⚙️ Cara Kerja

Bot bekerja dengan cara berikut:

1.  **Inisialisasi**: Saat dijalankan, bot akan membaca file `progress.json` untuk mengetahui pesan terakhir yang telah diekspor. Jika file tidak ada, bot akan memulai dari pesan paling awal di channel sumber.
2.  **Membaca Riwayat**: Bot membaca riwayat pesan di `SOURCE_CHANNEL` secara kronologis.
3.  **Mengelompokkan Pesan**: Bot akan mengumpulkan pesan-pesan yang dikirim oleh pengguna yang sama. Sebuah "kelompok" dianggap selesai jika:
    - Pesan berikutnya dikirim oleh pengguna yang berbeda.
    - Jeda waktu antara pesan saat ini dan pesan sebelumnya melebihi `GROUP_SECONDS`.
4.  **Mengirim via Webhook**: Setelah satu kelompok pesan terkumpul, bot akan mengirimkannya ke `TARGET_CHANNEL` melalui webhook:
    - Teks dari semua pesan dalam kelompok digabungkan.
    - Lampiran dari semua pesan dalam kelompok dikirim satu per satu.
    - Nama dan avatar pengirim asli digunakan pada setiap kiriman.
5.  **Menyimpan Progres**: Setelah setiap kelompok berhasil dikirim, ID pesan terakhir dalam kelompok tersebut disimpan ke `progress.json`.

## 🚀 Prasyarat

Sebelum memulai, pastikan Anda memiliki:

- Python 3.8 atau lebih baru.
- Akun Discord dengan izin untuk membuat aplikasi dan bot.
- Sebuah [Aplikasi Bot Discord](https://discord.com/developers/applications).
  - Pastikan Anda telah mengaktifkan **Privileged Gateway Intents** (`Server Members Intent` dan `Message Content Intent`) di pengaturan bot Anda.

## 📦 Instalasi & Konfigurasi

Ikuti langkah-langkah berikut untuk menjalankan bot:

**1. Kloning Repositori**

```bash
git clone https://github.com/RfadnjdExt/ArchiveBot.git
cd ArchiveBot
```

**2. Instal Dependensi**
Disarankan menggunakan _virtual environment_.

```bash
python -m venv venv
source venv/bin/activate  # Untuk Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**3. Konfigurasi Environment**
Buat file bernama `.env` di direktori utama proyek dan isi dengan variabel berikut:

```env
# Token bot Anda dari Discord Developer Portal
BOT_TOKEN=your_discord_bot_token_here

# ID channel tempat pesan akan diambil
SOURCE_CHANNEL_ID=id_channel_sumber_anda

# ID channel tempat pesan akan dikirim
TARGET_CHANNEL_ID=id_channel_target_anda

# (Opsional) Token API dari lewd.host untuk mengunggah file > 10MB
# Jika tidak diisi, file besar akan dilewati.
LEWDHOST_TOKEN=your_lewdhost_api_token_here
```

**Cara Mendapatkan ID Channel:**
Aktifkan _Developer Mode_ di Discord (`Settings > Advanced > Developer Mode`). Kemudian, klik kanan pada channel yang diinginkan dan pilih "Copy Channel ID".

**4. Undang Bot ke Server Anda**
Undang bot ke server Discord Anda dengan izin berikut:

- `Read Messages/View Channels`
- `Read Message History`
- `Send Messages`
- `Manage Webhooks`
- `Attach Files`

## ▶️ Menjalankan Bot

Setelah semua konfigurasi selesai, jalankan bot dengan perintah:

```bash
python main.py
```

Bot akan online, memulai proses ekspor, dan mencatat progresnya di konsol. Anda dapat menghentikannya kapan saja dengan `Ctrl+C`, dan progres akan tersimpan dengan aman.

## 🔧 Kustomisasi Lanjutan

Anda dapat mengubah konstanta berikut di dalam skrip untuk menyesuaikan perilaku bot:

| Variabel             | Nilai Default | Deskripsi                                                                  |
| -------------------- | ------------- | -------------------------------------------------------------------------- |
| `DELAY`              | `1.5`         | Jeda (detik) antar pengiriman untuk menghindari _rate limit_.              |
| `GROUP_SECONDS`      | `300`         | Jeda waktu maksimal (detik) antar pesan agar masih dianggap satu kelompok. |
| `MAX_FILE_SIZE`      | `10 MB`       | Ukuran file maksimal untuk diunggah langsung ke Discord.                   |
| `MAX_LEWD_HOST_SIZE` | `512 MB`      | Ukuran file maksimal untuk diunggah ke host eksternal.                     |
| `WEBHOOK_NAME`       | `ArchiveBot`  | Nama webhook yang akan dibuat di channel target.                           |

## ⚠️ Peringatan

- Proses ekspor untuk channel dengan riwayat yang sangat panjang bisa memakan waktu lama.
- Pastikan bot memiliki izin yang benar di kedua channel (sumber dan target).
- Penggunaan host eksternal untuk file besar bergantung pada ketersediaan dan kebijakan layanan tersebut ([lewd.host](https://lewd.host/)).

## 📜 Lisensi

Proyek ini dilisensikan di bawah [Lisensi MIT](LICENSE).
