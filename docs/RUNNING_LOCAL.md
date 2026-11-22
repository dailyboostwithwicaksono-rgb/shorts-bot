# Panduan Menjalankan shorts-bot di Lokal (Windows)

Panduan ini dibuat **bertahap dan detail** untuk menjalankan proses pembuatan video **di laptop (lokal)**, tanpa bergantung pada GitHub Actions.

> **Asumsi panduan ini:** kamu awam/baru pertama kali. Ikuti langkah berurutan. Bagian bertanda **KRUSIAL** adalah hal yang paling sering menjadi penyebab gagal — periksa itu dulu jika ada error.

---

## 0. Gambaran singkat (apa yang terjadi)

Alur saat dijalankan lokal (mode default `list`):
1. **Rencana** (`scripts/plan.py`): memilih 1 quote dari `data/quotes.json` (berurutan), menentukan **kata kunci** dari isi quote (AI teks, 1 langkah; ada fallback heuristik jika AI tidak tersedia) → mencari & mengunduh **latar video dari Pixabay Video API** (filter oleh kode: tanpa animasi, durasi/kualitas progresif, pilih acak 1 dari hingga 3; fallback ke cache `data/pixabay_cache.json`) → memilih & mengunduh **musik** dari **Freetouse Public API** (non-premium, tema calm/motivasi, durasi memadai; fallback ke file lokal jika API gagal) → menulis `render_plan.json` dan mencatat log/metadata (`data/used_quotes.jsonl`, `data/used_videos.jsonl`, `data/used_music.jsonl`, serta update `data/pixabay_cache.json` bila sukses).
2. **Render** (`scripts/render.py`): memakai **ffmpeg/ffprobe** untuk merender latar (grayscale + overlay hitam ~30% + band teks ber-gradasi/feather, durasi disesuaikan — jika sumber lebih pendek akan diperlambat agar pas), teks (font Montserrat, sudah ada di repo), dan musik menjadi video akhir.
3. **Hasil**: tersimpan di folder `out/` — siap untuk **upload manual** ke YouTube.

**Yang tetap butuh internet:** akses Pixabay API & unduh latar video, akses Freetouse API & unduh musik, dan (opsional/tergantung mode) panggil AI.  
**Yang TIDAK otomatis saat upload manual:** upload ke YouTube & arsip ke Drive (kamu lakukan sendiri), sehingga **tidak butuh OAuth Google** untuk langkah-langkah itu.

**Penyimpanan (lokal/GitHub):** file media (video latar & musik) diunduh ke `work/` saat proses dan hasil render ke `out/` — folder ini **tidak di-commit** (`.gitignore`) sehingga tidak menambah storage repo. Yang disimpan/di-commit adalah **metadata/log** pemakaian: `data/used_quotes.jsonl`, `data/pixabay_cache.json`, `data/used_videos.jsonl`, `data/used_music.jsonl`.

**File hasil penting (untuk upload manual):**
- `out/final.mp4` → file video
- `out/caption.txt` → **deskripsi/caption siap tempel** (sudah berisi kredit quote, hashtag, atribusi Pixabay & musik Freetouse)
- `out/manifest.json` → berisi `title`, `caption`, `hashtags`, `description`, metadata latar/musik/render

---

## 1. Kebutuhan & cek kesiapan

### 1.1 Perkiraan kebutuhan
- **Laptop/CPU**: render video pendek 1080×1920 (15–30 dtk) ringan untuk CPU modern — biasanya ±1–2 menit/video.
- **RAM**: 8 GB umumnya cukup.
- **Disk**: siapkan ruang kosong (disarankan beberapa GB). File sementara/hasil (latar unduhan, musik, PNG overlay, MP4) memakan puluhan–ratusan MB per proses. **KRUSIAL:** jika disk hampir penuh, render/unduh bisa gagal.
- **Internet**: stabil (Pixabay API + unduh video, Freetouse API + unduh musik; AI jika dipakai).
- **Sistem**: Windows (panduan ini memakai PowerShell).

### 1.2 Perangkat lunak
| Komponen | Wajib? | Catatan |
|---|---|---|
| Python 3.10+ | Ya | Cek: `python --version` |
| Dependensi Python (`requests`, `Pillow`) | Ya | Dari `requirements.txt` |
| **ffmpeg** & **ffprobe** | **Ya (KRUSIAL)** | Untuk render video & deteksi durasi latar. Tanpa ini, proses render pasti gagal |
| API key **Pixabay** | **Ya (latar)** | `PIXABAY_API_KEY` (kecuali bisa pakai fallback cache yang sudah ada & valid) |
| API key AI (OpenRouter/Gemini/DeepSeek) | Disarankan | Untuk keyword latar relevan & mode/metadata AI. Keyword punya fallback heuristik, tetapi hasil relevansi bisa berbeda |
| Musik Freetouse API | Ya (otomatis) | Diambil otomatis per run (tanpa API key), butuh internet. Fallback: file lokal di `work/music/` jika API gagal |
| Font Montserrat | Sudah ada | Dibundle di `assets/fonts/` (tidak perlu instal) |

---

## 2. Kenali folder & file penting
Buka folder repo, misalnya: `C:\Users\LENOVO\shorts-bot`

- `data/quotes.json` — daftar quote (sumber mode `list`).
- `data/used_quotes.jsonl` — log quote yang sudah dipakai (akan bertambah tiap run).
- `data/pixabay_cache.json` — cache latar Pixabay yang pernah berhasil (fallback; diperbarui saat sukses).
- `data/used_videos.jsonl` — metadata semua latar video yang pernah dipakai (akan bertambah tiap run).
- `data/used_music.jsonl` — metadata semua musik yang pernah dipakai (akan bertambah tiap run).
- `config/themes.json` — pengaturan tipografi/layout/gaya visual, path metadata, dan (opsional) fallback musik lokal.
- `work/` — folder kerja sementara (dibuat saat jalan): `work/bg.mp4` (latar unduhan), `work/music/freetouse_bg.mp3` (musik unduhan). **Tidak di-commit**.
- `out/` — hasil: `final.mp4`, `caption.txt`, `manifest.json`. **Tidak di-commit**.
- `assets/fonts/` — font Montserrat (jangan dihapus).
- `scripts/` — skrip (`plan.py`, `render.py`, `pixabay.py`, `freetouse.py`, dll).

> **Jangan commit:** `.env`, folder `work/`, folder `out/`, `render_plan.json` (sudah di `.gitignore`). File log/metadata di `data/*.jsonl` dan `data/pixabay_cache.json` memang **di-commit** untuk riwayat.

---

## 3. Langkah 1 — Pasang dependensi Python

1. Buka **PowerShell**.
2. Masuk ke folder repo:
   ```powershell
   cd C:\Users\LENOVO\shorts-bot
   ```
3. (Disarankan, opsional) buat virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   Jika aktivasi diblokir, lewati venv atau jalankan `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (sekali) lalu coba lagi.
4. Pasang dependensi:
   ```powershell
   pip install -r requirements.txt
   ```
   **Tanda berhasil:** tidak ada error merah; `requests` dan `Pillow` terpasang.

**Cek cepat:**
```powershell
python -c "import requests, PIL; print('ok')"
```

> **KRUSIAL:** Jika `python`/`pip` tidak dikenali, pastikan Python terpasang dan ada di PATH (buka terminal baru).

---

## 4. Langkah 2 — Pasang ffmpeg & ffprobe (**KRUSIAL**)

ffmpeg/ffprobe dipakai untuk merender video dan mendeteksi durasi latar.

### Cara memasang (pilih salah satu)
- **Winget (Windows 10/11):**
  ```powershell
  winget install Gyan.FFmpeg
  ```
  (atau cari paket: `winget search ffmpeg`)
- **Manual:** unduh build ffmpeg untuk Windows, ekstrak, lalu tambahkan folder `bin` (berisi `ffmpeg.exe` & `ffprobe.exe`) ke **PATH**.

### Cek (wajib)
Tutup lalu buka PowerShell baru, masuk ke folder repo, lalu:
```powershell
ffmpeg -version
ffprobe -version
```
**Tanda berhasil:** keduanya menampilkan versi.

> **KRUSIAL:** Jika setelah pasang masih “tidak dikenali”, PATH belum benar atau terminal belum di-restart. Pastikan folder `bin` ada di PATH, lalu buka terminal baru. Jika baru saja terpasang, nilai PATH di terminal lama tidak berubah.

---

## 5. Langkah 3 — Musik (otomatis via Freetouse API)

Pada alur saat ini, musik **tidak perlu disiapkan manual**: `plan.py` mengambil track dari **Freetouse Public API** secara otomatis per run (tanpa API key), memilih yang **non-premium** & dapat dipakai, bertema/mood **calm/motivasi** (inspirational, motivational, calm, uplifting, peaceful, ambient, piano, cinematic, nature, dll.) dengan durasi memadai, lalu mengunduhnya ke `work/music/freetouse_bg.mp3`.

**Syarat:** koneksi internet stabil ke `api.freetouse.com`.

**Fallback lokal (otomatis, jika API gagal):** skrip akan mencoba file musik lokal di `work/music/` (termasuk yang terdaftar di `config/themes.json`) bila tersedia. Jika API gagal dan tidak ada file lokal, proses berhenti dengan pesan error yang jelas.

> **KRUSIAL:** Pastikan internet aktif. Tidak perlu rclone/Google Drive/service account untuk musik. File musik yang diunduh bersifat sementara (di `work/`, tidak di-commit); metadata musik yang dipakai dicatat di `data/used_music.jsonl`.

---

## 6. Langkah 4 — Siapkan variabel lingkungan (env) (**KRUSIAL: PIXABAY_API_KEY & internet**)

Skrip membaca environment variable. Di PowerShell, set untuk **sesi saat ini** dengan `$env:NAMA = "nilai"`.  
`plan.py` juga akan memuat file `.env` di root repo (jika ada) untuk variabel yang belum ada di environment — jadi kamu bisa menyimpannya di `.env` lokal (**jangan di-commit**).

### Wajib untuk latar Pixabay
```powershell
$env:PIXABAY_API_KEY = "ISI_API_KEY_PIXABAY_KAMU"
```
Atau simpan di `.env`: `PIXABAY_API_KEY=...`

> **KRUSIAL:** Tanpa `PIXABAY_API_KEY`, pengambilan latar Pixabay gagal. Jika `data/pixabay_cache.json` berisi entri yang masih bisa diunduh, sistem dapat mencoba fallback cache; jika tidak, proses berhenti dengan error jelas. Musik dari Freetouse API tidak butuh key, tetapi tetap butuh internet.

### Mode & AI (untuk keyword latar / mode konten)
- **Mode default `list`**: memilih quote dari `data/quotes.json`. Keyword latar idealnya dibuat AI (1 langkah, teks saja). Jika `OPENROUTER_API_KEY` (atau provider lain yang dikonfigurasi) **tidak** tersedia, sistem memakai **fallback heuristik** untuk keyword (tetap berjalan, relevansi bisa berbeda).
- **Mode `famous` / `custom`**: memerlukan AI untuk kurasi/metadata (sesuai konfigurasi).

Contoh (opsional, untuk AI):
```powershell
$env:OPENROUTER_API_KEY = "ISI_API_KEY_KAMU"
$env:AI_PROVIDER = "openrouter"
$env:OPENROUTER_MODEL = "nvidia/nemotron-3.5-lightning:free"
$env:QUOTE_MODE = "list"   # atau famous/custom
```
(Opsional) tanggal run: `$env:RUN_DATE = "2026-11-19"`.

> **KRUSIAL:** Jangan pernah membagikan/commit API key atau file kredensial. Jika key sempat terekspos, segera **rotasi**.

---

## 7. Langkah 5 — Jalankan rencana (plan)

```powershell
python scripts/plan.py
```

**Apa yang dilakukan:**
- Memilih mode/quote (default `list`, berurutan & belum terpakai).
- Membuat kata kunci latar dari quote (AI/fallback), mencari di Pixabay, memfilter (tanpa animasi, durasi/kualitas progresif), memilih **acak 1 dari hingga 3** kandidat, mengunduh ke `work/bg.mp4` (butuh internet & `PIXABAY_API_KEY`). Jika kosong → coba cache `data/pixabay_cache.json`.
- Memilih & mengunduh musik dari Freetouse API ke `work/music/freetouse_bg.mp3` (non-premium, tema calm/motivasi, durasi memadai; butuh internet). Jika gagal → coba fallback file lokal bila ada.
- Menulis `render_plan.json`, menambah log `data/used_quotes.jsonl`, `data/used_videos.jsonl`, `data/used_music.jsonl`, dan dapat memperbarui `data/pixabay_cache.json`.

**Tanda berhasil:** muncul `[ok] ... rencana ditulis ... log ditambah ...` dan file `render_plan.json` ada.

> **KRUSIAL (cek jika gagal):** Pixabay/key/koneksi/rate limit/kosong & cache tidak tersedia → cek `PIXABAY_API_KEY`, internet, atau isi cache. Musik Freetouse gagal/kosong → cek koneksi internet ke Freetouse (atau sediakan file lokal fallback di `work/music/`). AI gagal → periksa key/model; keyword tetap punya fallback, mode `famous/custom` butuh AI. Disk penuh → kosongkan ruang.

---

## 8. Langkah 6 — Render video

```powershell
python scripts/render.py
```

**Apa yang dilakukan:** membaca `render_plan.json`, merender teks (Montserrat, fade-in progresif) dan menggabungkan dengan latar (grayscale, overlay ~30%, band feather; durasi dideteksi & disesuaikan — diperlambat bila lebih pendek dari target) + musik via ffmpeg.

**Tanda berhasil:** muncul `[ok] render selesai: ...out\final.mp4 (...)` dan folder `out/` berisi `final.mp4`, `caption.txt`, `manifest.json`.

> **KRUSIAL:** `ffmpeg/ffprobe` harus dikenali (langkah 2). `render_plan.json` harus ada (langkah 5). Pastikan `assets/fonts/` utuh. File di `work/` dan `out/` bersifat sementara/lokal (tidak di-commit).

---

## 9. Langkah 7 — Ambil hasil untuk upload manual ke YouTube

1. Buka folder `out/`.
2. **Video**: unggah `final.mp4` ke YouTube (YouTube Studio, sebagai Shorts).
3. **Judul**: salin dari `out/manifest.json` → `title`.
4. **Deskripsi** (siap tempel, termasuk kredit quote, hashtag, dan atribusi **Pixabay** & **Freetouse**): salin isi `out/caption.txt`.
5. (Opsional) **Tag/hashtag**: `manifest.json` → `hashtags`.

> **Catatan lisensi/atribusi:** latar dari Pixabay dan musik dari Freetouse sesuai ketentuan sumber — deskripsi yang dihasilkan sudah menyertakan atribusi; tetap patuhi lisensi masing-masing (https://freetouse.com/license). File media `work/`/`out/` tidak disimpan ke repo; metadata pemakaian tercatat di `data/used_videos.jsonl` dan `data/used_music.jsonl`.

---

## 10. (Opsional) Arsip ke Drive / upload otomatis & OAuth

- **Arsip otomatis ke Drive** (`python scripts/archive_drive.py`) dan **Upload otomatis** (`python scripts/publish.py`) butuh OAuth user (`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, dst.). Untuk pemula, **arsip/upload manual** lebih sederhana.
- **Publish (dispatcher, Fase 3–4):** `publish.py` membaca konten kanonik dari `out/` dan mem-publish ke target aktif. Default `PUBLISH_TARGETS=youtube` (perilaku sama). Opsi: `PUBLISH_DRY_RUN=1` (formatter/validasi tanpa upload), `PUBLISH_FAIL_FAST` (default `1`). Target tambahan `tiktok,meta,x` tersedia sebagai kerangka (formatter + stub/dry-run); publish nyata bertahap dan butuh kredensial/izin/API & implementasi platform masing-masing. Contoh dry-run lokal: set `PUBLISH_TARGETS=youtube,tiktok` dan `PUBLISH_DRY_RUN=1` lalu jalankan `python scripts/publish.py`.
- Alur lokal **upload manual** tidak memerlukan OAuth user, rclone, maupun service account.

---

## 11. (Opsional) Menjadwalkan otomatis di lokal (Task Scheduler)

1. Buat `run_local.bat` yang menjalankan (set env, lalu) `python scripts/plan.py` dan `python scripts/render.py` (pastikan PATH menyertakan ffmpeg).
2. **Task Scheduler** → Create Basic Task → jadwal → Action *Start a program* → arahkan ke batch, *Start in* = folder repo.
3. Pastikan laptop menyala, ada **internet** (Pixabay + Freetouse API), dan `PIXABAY_API_KEY` tersedia (env/.env). Musik diunduh otomatis per run.

---

## 12. Cek krusial saat error atau gagal

| Gejala / pesan | Penyebab umum | Yang harus dicek / lakukan (**KRUSIAL**) |
|---|---|---|
| `python` / `pip` tidak dikenali | Python belum terpasang/PATH salah | Pasang Python, centang “Add to PATH”, buka terminal baru |
| `No module named ...` (requests/PIL) | Dependensi belum terpasang | `pip install -r requirements.txt` |
| `ffmpeg` / `ffprobe` tidak dikenali | Belum terpasang / PATH / terminal lama | Pasang ffmpeg, cek `ffmpeg -version` & `ffprobe -version` di terminal baru |
| `PIXABAY_API_KEY` tidak ditemukan / Pixabay gagal | Key kosong/salah, rate limit/kuota, koneksi | **KRUSIAL:** set `PIXABAY_API_KEY` (env/.env), cek internet/kuota. Rotasi key jika terekspos |
| Tidak ada video Pixabay cocok & cache kosong/tidak bisa dipakai | Hasil pencarian kosong + cache tidak tersedia | Cek koneksi/key; pastikan `data/pixabay_cache.json` berisi entri valid (akan terisi setelah run sukses) |
| Musik Freetouse gagal / tidak ada track cocok | Koneksi ke `api.freetouse.com` bermasalah, API sementara tidak bisa diakses, atau filter ketat | **KRUSIAL:** cek internet. Skrip memilih track non-premium bertema calm/motivasi dengan durasi memadai; jika API gagal dan tidak ada file lokal fallback di `work/music/`, proses berhenti — coba lagi nanti atau sediakan file lokal fallback |
| AI gagal / 401 / 429 / provider gagal | Key/model/kuota bermasalah | Cek `OPENROUTER_API_KEY` & model; keyword latar punya fallback, mode `famous/custom` butuh AI |
| `render_plan.json` tidak ada saat render | Plan belum/gagal | Jalankan `python scripts/plan.py` dulu |
| Font tidak ditemukan | Folder font hilang | Pastikan `assets/fonts/` berisi file Montserrat |
| Error tulis file / disk penuh | Ruang disk habis | **KRUSIAL:** kosongkan disk, hapus isi lama `out/`/`work/` (file media tidak perlu disimpan) |
| `invalid_grant` (arsip/upload otomatis) | Token OAuth bermasalah | Regenerate `YT_REFRESH_TOKEN` atau lakukan upload/arsip manual |

### Urutan cek cepat jika “gagal total”
1. Baca pesan error (baris penyebab).
2. Cek dasar: `ffmpeg -version` & `ffprobe -version`, `PIXABAY_API_KEY` ter-set, internet OK (Pixabay & Freetouse), disk tidak penuh.
3. Jalankan bertahap: `python scripts/plan.py` lalu `python scripts/render.py`.
4. Isolasi: mode `list` dengan koneksi internet OK (latar dari Pixabay/cache, musik dari Freetouse).

---

## 13. Catatan penting
- **Sumber latar:** dari **Pixabay Video API** (bukan Pexels/Drive), dengan filter metadata oleh kode & fallback cache `data/pixabay_cache.json`.
- **Sumber musik:** dari **Freetouse Public API** (tanpa key), track non-premium/usable bertema calm/motivasi & durasi memadai, diunduh per run; fallback ke file lokal jika tersedia. Atribusi di deskripsi (judul, artis, URL best-effort) — patuhi lisensi: https://freetouse.com/license.
- **Penyimpanan & metadata:** file media (`work/`, `out/`, `render_plan.json`) **tidak di-commit** (ephemeral) agar tidak menambah storage repo. Metadata/log pemakaian **di-commit**: `data/used_quotes.jsonl`, `data/pixabay_cache.json`, `data/used_videos.jsonl`, `data/used_music.jsonl`.
- **Keamanan**: jangan commit `.env` atau rahasia lain. Rotasi key jika pernah terekspos.
- **Lisensi/atribusi**: patuhi lisensi Pixabay & Freetouse; deskripsi yang dihasilkan menyertakan atribusi.
