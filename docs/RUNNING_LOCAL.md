# Panduan Menjalankan shorts-bot di Lokal (Windows)

Panduan ini dibuat **bertahap dan detail** untuk menjalankan proses pembuatan video **di laptop (lokal)**, tanpa bergantung pada GitHub Actions.

> **Asumsi panduan ini:** kamu awam/baru pertama kali. Ikuti langkah berurutan. Bagian bertanda **KRUSIAL** adalah hal yang paling sering menjadi penyebab gagal — periksa itu dulu jika ada error.

---

## 0. Gambaran singkat (apa yang terjadi)

Alur saat dijalankan lokal (mode default `list`):
1. **Rencana** (`scripts/plan.py`): memilih 1 quote dari `data/quotes.json` (berurutan), mengunduh **latar video dari Pexels** (internet), memilih **musik** dari folder lokal `work/music/`, lalu menulis `render_plan.json` dan mencatat log ke `data/used_quotes.jsonl`.
2. **Render** (`scripts/render.py`): memakai **ffmpeg** untuk menggabungkan latar + teks (font Montserrat, sudah ada di repo) + musik menjadi video akhir.
3. **Hasil**: tersimpan di folder `out/` — siap untuk **upload manual** ke YouTube.

**Yang tetap butuh internet:** unduh latar Pexels, (opsional) panggil AI, dan akses Drive jika kamu memilih mengunduh musik via rclone.  
**Yang TIDAK otomatis saat upload manual:** upload ke YouTube & arsip ke Drive (kamu lakukan sendiri), sehingga **tidak butuh OAuth Google** untuk langkah-langkah itu.

**File hasil penting (untuk upload manual):**
- `out/final.mp4` → file video
- `out/caption.txt` → **deskripsi/caption siap tempel** (sudah berisi kredit quote, hashtag, atribusi Pexels & musik)
- `out/manifest.json` → berisi `title`, `caption`, `hashtags`, `description`

---

## 1. Kebutuhan & cek kesiapan

### 1.1 Perkiraan kebutuhan
- **Laptop/CPU**: render video pendek 1080×1920 (15–30 dtk) ringan untuk CPU modern (contoh: i5 generasi baru) — biasanya ±1–2 menit/video.
- **RAM**: 8 GB umumnya cukup.
- **Disk**: siapkan ruang kosong (disarankan beberapa GB). File sementara/hasil (bg, musik, PNG overlay, MP4) memakan puluhan–ratusan MB per proses. **KRUSIAL:** jika disk hampir penuh, render/unduh bisa gagal.
- **Internet**: stabil (untuk unduh latar Pexels; dan AI jika dipakai).
- **Sistem**: Windows (panduan ini memakai PowerShell).

### 1.2 Perangkat lunak
| Komponen | Wajib? | Catatan |
|---|---|---|
| Python 3.10+ | Ya | Cek: `python --version` |
| Dependensi Python (`requests`, `Pillow`) | Ya | Dari `requirements.txt` |
| **ffmpeg** (& `ffprobe`) | **Ya (KRUSIAL)** | Untuk render video. Tanpa ini, proses render pasti gagal |
| rclone | Opsional | Hanya jika ingin unduh musik dari Google Drive via service account. Alternatif mudah: salin mp3 manual ke `work/music/` |
| Font Montserrat | Sudah ada | Dibundle di `assets/fonts/` (tidak perlu instal) |

> **Catatan:** Di laptop contoh proyek ini, Python sudah terpasang, tetapi **ffmpeg & rclone belum terpasang** — jadi kamu perlu memasang ffmpeg (langkah 3).

---

## 2. Kenali folder & file penting
Buka folder repo, misalnya: `C:\Users\LENOVO\shorts-bot`

- `data/quotes.json` — daftar quote (sumber mode `list`).
- `data/used_quotes.jsonl` — log quote yang sudah dipakai (akan bertambah tiap run).
- `config/themes.json` — pengaturan (tipografi/layout) & pool media (Pexels, musik).
- `work/` — folder kerja (dibuat saat jalan): `work/bg.mp4` (latar unduhan), `work/music/` (file musik).
- `out/` — hasil: `final.mp4`, `caption.txt`, `manifest.json`.
- `assets/fonts/` — font Montserrat (jangan dihapus).
- `scripts/` — skrip (`plan.py`, `render.py`, dll).

> **Jangan commit/simpan ke git:** `.env`, `sa.json`, folder `work/`, folder `out/` (sudah di `.gitignore`).

---

## 3. Langkah 1 — Pasang dependensi Python

1. Buka **PowerShell**.
2. Masuk ke folder repo:
   ```powershell
   cd C:\Users\LENOVO\shorts-bot
   ```
3. (Disarankan, opsional tapi baik) buat virtual environment agar rapi:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   Jika aktivasi diblokir kebijakan, kamu bisa lewati venv dan pasang langsung, atau jalankan: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (sekali), lalu coba aktifkan lagi.
4. Pasang dependensi:
   ```powershell
   pip install -r requirements.txt
   ```
   **Tanda berhasil:** tidak ada pesan error merah; paket `requests` dan `Pillow` terpasang.

**Cek cepat:**
```powershell
python -c "import requests, PIL; print('ok')"
```
Jika muncul `ok`, dependensi siap.

> **KRUSIAL:** Jika `python` tidak dikenali, Python belum terpasang atau belum ada di PATH — pasang Python terlebih dahulu dan centang opsi “Add Python to PATH” saat instalasi.

---

## 4. Langkah 2 — Pasang ffmpeg (**KRUSIAL**)

ffmpeg dipakai untuk merender video. Tanpa ini, `python scripts/render.py` akan gagal.

### Cara memasang (pilih salah satu)
- **Winget (sering tersedia di Windows 10/11):**
  ```powershell
  winget install Gyan.FFmpeg
  ```
  (atau cari paket ffmpeg lain yang tersedia: `winget search ffmpeg`)
- **Manual:** unduh build ffmpeg untuk Windows (mis. dari gyan.dev / BtbN), ekstrak, lalu tambahkan folder `bin`-nya ke **PATH** environment variable.

### Cek (wajib)
Tutup lalu buka PowerShell baru, masuk ke folder repo, lalu:
```powershell
ffmpeg -version
ffprobe -version
```
**Tanda berhasil:** kedua perintah menampilkan informasi versi (bukan pesan “tidak dikenali”).

> **KRUSIAL:** Jika setelah pasang masih “tidak dikenali”, PATH belum benar — pastikan folder yang berisi `ffmpeg.exe` dan `ffprobe.exe` ada di PATH, lalu buka terminal baru.

---

## 5. Langkah 3 — Siapkan musik di `work/music/`

Skrip memilih musik **secara acak** dari pool di `config/themes.json`, tetapi **hanya file yang benar-benar ada** di `work/music/`.

### Cara termudah (disarankan untuk pemula): salin manual
1. Buat folder musik:
   ```powershell
   mkdir work\music -Force
   ```
2. Unduh file musik dari Google Drive folder `shorts-music` (lewat browser) ke komputer.
3. Letakkan di `work\music\` dengan **nama file persis** sesuai config, misalnya:
   - `work\music\unstoppable.mp3`
   - `work\music\enlivening.mp3`
4. Cek:
   ```powershell
   dir work\music
   ```
   Pastikan minimal satu file mp3 yang namanya cocok ada di sana.

> **KRUSIAL:** Nama file harus **sama persis** dengan `file` di `config/themes.json` (termasuk huruf kecil/besar & ekstensi). Jika tidak ada yang cocok, `plan.py` akan berhenti dengan pesan “Tidak ada file musik…”.

### (Opsional, lebih teknis) unduh via rclone + Service Account
- Pasang rclone, siapkan `sa.json` (service account) dan ID folder musik, lalu salin isi folder ke `work/music/`. Ini meniru cara di GitHub Actions (baca Drive, SA perlu akses Viewer ke folder). Tidak wajib jika kamu menyalin manual.

---

## 6. Langkah 4 — Siapkan variabel lingkungan (env)

Skrip membaca beberapa nilai dari environment variable. Di PowerShell, set untuk **sesi saat ini** dengan `$env:NAMA = "nilai"`.

### Minimal untuk mode `list` (default, disarankan mulai dari sini)
Mode `list` memilih quote dari `data/quotes.json` dan membuat judul/caption sederhana **tanpa memanggil AI**, jadi **tidak butuh API key AI**.

```powershell
$env:QUOTE_MODE = "list"
```
(Opsional) tanggal run: `$env:RUN_DATE = "2026-11-19"` (jika tidak diisi, pakai tanggal hari ini).

### Jika memakai mode `famous` atau `custom` (butuh AI untuk metadata/kurasi)
```powershell
$env:OPENROUTER_API_KEY = "ISI_API_KEY_KAMU"
$env:AI_PROVIDER = "openrouter"
$env:OPENROUTER_MODEL = "inclusionai/ling-3.2-flash:free"
$env:QUOTE_MODE = "famous"   # atau "custom"
```
- Mode `custom` juga memakai: `QUOTE_TEXT`, `QUOTE_AUTHOR` (default `dbcw`), `QUOTE_LANGUAGE` (`auto/id/en`).

> **Catatan:** Variabel yang di-set dengan `$env:...` hanya berlaku di **jendela PowerShell yang sama**. Jika tutup terminal, set lagi sebelum run berikutnya. (Alternatif: simpan di file `.env` dan muat sesuai kebutuhan; jangan commit `.env`.)
> **KRUSIAL:** Jangan pernah membagikan/commit API key atau file kredensial (`sa.json`).

---

## 7. Langkah 5 — Jalankan rencana (plan)

Pastikan kamu di folder repo dan (jika pakai) env sudah diset.

```powershell
python scripts/plan.py
```

**Apa yang dilakukan:**
- Mengunduh 1 latar acak dari pool Pexels ke `work/bg.mp4` (butuh internet).
- Memilih 1 musik acak dari `work/music/`.
- Mode `list`: memilih quote berikutnya (berurutan, belum terpakai) dari `data/quotes.json`.
- Menulis `render_plan.json` dan menambah baris log ke `data/used_quotes.jsonl`.

**Tanda berhasil:** muncul pesan `[ok] ... rencana ditulis ... log ditambah ...` dan file `render_plan.json` ada di root repo.

> **KRUSIAL (cek jika gagal):** pesan “Tidak ada file musik…” → perbaiki isi/nama file di `work/music/` (langkah 3). Gagal unduh Pexels/koneksi → cek internet atau `file_url` di `config/themes.json`. Mode `famous` gagal karena AI → cek `OPENROUTER_API_KEY`/model/kuota (atau pakai `QUOTE_MODE=list`).

---

## 8. Langkah 6 — Render video

```powershell
python scripts/render.py
```

**Apa yang dilakukan:** membaca `render_plan.json`, merender teks (Montserrat, fade-in progresif) dan menggabungkan dengan latar + musik via ffmpeg.

**Tanda berhasil:** muncul `[ok] render selesai: ...out\final.mp4 (...)` dan folder `out/` berisi:
- `final.mp4`
- `caption.txt`
- `manifest.json`

> **KRUSIAL:** Jika `ffmpeg/ffprobe tidak dikenali` → pasang & perbaiki PATH (langkah 2). Jika `render_plan.json` tidak ada → jalankan langkah 5 dulu. Jika error font/file → pastikan folder `assets/fonts/` utuh.

---

## 9. Langkah 7 — Ambil hasil untuk upload manual ke YouTube

1. Buka folder `out/`.
2. **Video**: unggah `final.mp4` ke YouTube (YouTube Studio, sebagai Shorts).
3. **Judul**: salin dari `out/manifest.json` → field `title`.
4. **Deskripsi** (siap tempel, sudah termasuk kredit quote, hashtag, dan atribusi Pexels/musik): salin isi `out/caption.txt` (sama dengan `manifest.json` → `description`).
5. (Opsional) **Tag/hashtag**: lihat `manifest.json` → `hashtags`.

Dengan upload manual, kamu **tidak perlu** OAuth app/Google approval untuk langkah upload.

> **Catatan:** Latar dari Pexels & musik dari freetouse.com memiliki ketentuan lisensi/atribusi — deskripsi yang dihasilkan sudah menyertakan atribusi; tetap patuhi lisensi masing-masing sumber.

---

## 10. (Opsional) Arsip ke Drive / upload otomatis & OAuth

- **Arsip otomatis ke Drive** (`python scripts/archive_drive.py`): butuh OAuth user (scope Drive) — variabel `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `GDRIVE_OUTPUTS_FOLDER_ID`. Untuk pemula & menghindari kerumitan OAuth/approval, **arsipkan manual** saja (salin `out/` ke Drive).
- **Upload otomatis ke YouTube** (`python scripts/publish.py`): butuh OAuth user (scope YouTube upload). Jika tujuanmu upload manual, lewati langkah ini.

Mode **list + upload manual + musik disalin manual** dapat dijalankan **tanpa OAuth user Google** (mengurangi isu persetujuan/verifikasi app). Membaca musik via rclone+service account juga tidak memakai OAuth user.

---

## 11. (Opsional) Menjadwalkan otomatis di lokal (Task Scheduler)

Jika ingin jalan otomatis tanpa GitHub Actions:
1. Buat file batch, mis. `run_local.bat` di folder repo, yang menjalankan urutan (set env yang perlu, lalu `python scripts/plan.py` dan `python scripts/render.py`).
2. Buka **Task Scheduler** → Create Basic Task → atur jadwal (harian, jam yang diinginkan) → Action: *Start a program* → arahkan ke `run_local.bat`, dan set *Start in* ke folder repo (`C:\Users\LENOVO\shorts-bot`).
3. Pastikan laptop menyala/aktif pada jam jadwal, ada internet, dan musik tersedia di `work/music/`.

---

## 12. Cek krusial saat error atau gagal

Gunakan daftar ini: temukan gejala → cek penyebab & tindakan.

| Gejala / pesan | Penyebab umum | Yang harus dicek / lakukan (**KRUSIAL**) |
|---|---|---|
| `python` / `pip` tidak dikenali | Python belum terpasang atau tidak di PATH | Pasang Python, centang “Add to PATH”, buka terminal baru, cek `python --version` |
| `No module named ...` / `ModuleNotFoundError` (requests/PIL) | Dependensi belum terpasang (atau salah environment) | Jalankan `pip install -r requirements.txt` di folder repo (aktifkan venv jika dipakai) |
| `ffmpeg` / `ffprobe` tidak dikenali, atau render gagal karena ffmpeg | ffmpeg belum terpasang / PATH salah | Pasang ffmpeg, pastikan `ffmpeg -version` & `ffprobe -version` berhasil di terminal baru |
| `Tidak ada file musik di ...` | Folder `work/music/` kosong atau nama file tidak cocok | Buat `work/music/`, salin mp3, pastikan nama **persis** sama dengan `music.file` di `config/themes.json`; cek dengan `dir work\music` |
| Gagal unduh latar / error koneksi / 404 Pexels | Internet bermasalah atau `file_url` Pexels kedaluwarsa | Cek koneksi internet; jika 404, perbarui `file_url` di `config/themes.json` (pool `pexels_backgrounds`) |
| AI gagal / 401 / 429 / `Semua provider AI gagal` (mode `famous`/custom) | API key salah/kosong, model/kuota bermasalah | Cek `OPENROUTER_API_KEY`, `AI_PROVIDER`, `OPENROUTER_MODEL` (pakai model `:free` valid); coba lagi nanti. **Untuk menghindari AI**, gunakan `QUOTE_MODE=list` |
| `render_plan.json` tidak ada saat render | Belum menjalankan plan atau plan gagal | Jalankan `python scripts/plan.py` dulu dan pastikan sukses |
| Font tidak ditemukan / error terkait font | Folder font bundel hilang/berubah | Pastikan `assets/fonts/` berisi `Montserrat-LightItalic.ttf`, `Montserrat-SemiBoldItalic.ttf`, `Montserrat-Italic.ttf` |
| Error tulis file / disk penuh / `No space left on device` | Ruang disk hampir habis | **KRUSIAL:** kosongkan ruang disk (C:), hapus isi lama `out/`/`work/` yang tidak diperlukan, lalu coba lagi |
| Hasil video tidak sesuai durasi/teks | Data quote atau plan tidak sesuai | Cek entri di `data/quotes.json` (id, lines 1–5, emphasis, author, duration) dan isi `render_plan.json` yang terbentuk |
| `invalid_grant` (jika menjalankan arsip/upload otomatis) | Token OAuth kedaluwarsa/dicabut | Regenerate refresh token (`scripts/get_refresh_token.py`) dan perbarui kredensial; atau lakukan arsip/upload **manual** |

### Urutan cek cepat jika “gagal total”
1. Buka pesan error → baca baris paling bawah/yang menyebut penyebab.
2. Cek **KRUSIAL** dasar: `ffmpeg -version` & `ffprobe -version` OK, `dir work\music` ada file yang cocok, koneksi internet OK, disk tidak penuh.
3. Jalankan ulang bertahap: `python scripts/plan.py` lalu `python scripts/render.py` untuk melihat langkah mana yang gagal.
4. Untuk isolasi masalah: coba `QUOTE_MODE=list` (tanpa AI) dengan musik yang sudah ada di `work/music/`.

---

## 13. Catatan penting
- **Sumber latar:** saat ini dari **Pexels** (URL di config), bukan dari Google Drive. Musik bisa dari Drive (disalin/rclone) ke `work/music/`.
- **Log**: setiap run plan menambah `data/used_quotes.jsonl` (lokal). Jika ingin perilaku pemilihan quote `list` “seperti baru”, kelola file log ini dengan sadar.
- **Keamanan**: jangan commit `.env`, `sa.json`, atau rahasia lain. Simpan API key/kredensial secara pribadi.
- **Lisensi/atribusi**: patuhi lisensi Pexels & freetouse.com; deskripsi yang dihasilkan sudah mencantumkan atribusi.
