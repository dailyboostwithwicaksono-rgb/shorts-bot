# shorts-bot

Automasi YouTube Shorts bertema **quotes** dengan konsep **teks dulu, gambar belakang**. Latar video diambil dari Pexels, digelap dan diberi shape hitam supaya teks terbaca, lalu teks quote muncul bertahap diikuti baris penulis (miring). Musik dari freetouse.com. Semua proses di GitHub Actions (repo public = gratis unlimited), hasil diarsipkan ke Google Drive, lalu di-upload ke YouTube Shorts.

## Mode konten
- **Famous quotes (AI, default/schedule)**: AI memilih/membuat quotes terkenal. Jika quotes aslinya bahasa Inggris → tetap bahasa Inggris; selain itu → Bahasa Indonesia. Baris penulis ditampilkan sebagai `- Nama -` (miring). Prompt AI diberi riwayat `data/used_quotes.jsonl` agar menghindari pengulangan.
- **Custom quotes (insidental, bridge untuk Telegram bot nanti)**: jalankan manual **Actions → shorts-bot → Run workflow** dengan input `mode=custom`, `quote_text`, `quote_author` (default `dbcw`), `quote_language` (auto/id/en). Penulis ditampilkan sebagai `- dbcw -` (atau nama yang diisi), miring. Integrasi Telegram bot penuh belum dibuat; nanti bot bisa memicu workflow ini lewat GitHub API (`workflow_dispatch`) dengan input yang sama.

```
Pexels MP4 langsung --latar--> Runner GitHub (4 core / 16 GB)
Drive /music --rclone-->  |
                          +-- AI: quotes terkenal / metadata custom (TEKS SAJA, tanpa gambar)
                          +-- ffmpeg: gelap + black band + teks bertahap + penulis miring + musik
                          |
                          +--OAuth--> Drive /outputs/<tanggal>  (arsip + caption.txt)
                          +--API----> YouTube Shorts
                          +--commit-> data/used_quotes.jsonl   (log quotes terpakai)
```

Jadwal default: **06.00 dan 18.00 WIB** (cron `0 23 * * *` dan `0 11 * * *` dalam UTC).

## Catatan konsep soal token

- **Mengulang video latar dan backsound TIDAK menghemat token AI.** Token dibayar dari teks yang dikirim, bukan dari file video/musik.
- Yang benar-benar menghemat token adalah **tidak mengirim thumbnail/gambar ke AI**. Pipeline ini mengirim **teks saja**.
- Supaya konten tidak terasa statis, tema punya **pool kecil** `pexels_backgrounds` berisi URL MP4 langsung dari Pexels. Skrip memilih satu secara deterministik berdasarkan tanggal.
- Riwayat quotes terpakai disimpan di `data/used_quotes.jsonl` dan ikut dikirim (ringkas) ke prompt AI famous quotes untuk mengurangi pengulangan.

---

## 1. Repo GitHub (akun sekunder)

1. Buat repo **public**, misalnya `shorts-bot`.
2. `Settings -> Actions -> General -> Workflow permissions` -> **Read and write permissions** (dibutuhkan agar workflow bisa auto-commit `data/used_quotes.jsonl`).
3. Jangan pasang kartu pembayaran di akun sekunder. Repo public = Actions gratis unlimited, 4 core / 16 GB.
4. File `.env`, `sa.json`, folder `work/`, dan `out/` sudah masuk `.gitignore`. Jangan pernah di-commit. Log quotes yang **boleh** di-commit: `data/used_quotes.jsonl`.

---

## 2. Google Cloud (sekali saja)

### 2.1 Project dan API

1. Buka https://console.cloud.google.com/ lalu buat project baru, misalnya `shorts-bot`.
2. `APIs & Services -> Library`, aktifkan:
   - **Google Drive API**
   - **YouTube Data API v3**

### 2.2 Service account untuk Drive

1. `APIs & Services -> Credentials -> Create credentials -> Service account`.
2. Nama `shorts-bot` -> Create and continue -> Done.
3. Klik service account itu, tab **Keys -> Add key -> Create new key -> JSON -> Create**.
4. Simpan file `sa.json`. Catat email service account-nya, bentuknya:
   `shorts-bot@PROJECT-ID.iam.gserviceaccount.com`
5. Ubah jadi satu baris base64:

   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("sa.json"))
   ```

   atau:

   ```bash
   python scripts/encode_sa.py sa.json
   ```

6. Simpan hasilnya sebagai Secret `GDRIVE_SA_JSON`.

### 2.3 Folder Drive dan sharing

Bedakan dua folder:

| Folder | Isi | Akses |
| --- | --- | --- |
| `shorts-music` | File MP3 dari freetouse | Service account sebagai **Viewer** |
| `shorts-outputs` | Hasil render (dibuat otomatis per tanggal) | Di-upload lewat **OAuth user**, bukan service account |

1. Buat kedua folder di Google Drive.
2. Share `shorts-music` ke email service account dengan peran **Viewer**.
3. `shorts-outputs` **tidak perlu** di-share ke service account. Service account Google tidak punya storage quota, jadi tidak bisa menulis ke Drive pribadi. Upload arsip memakai token OAuth-mu sendiri.
4. Ambil ID folder dari URL. Contoh:
   `https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrSt`
   -> ID-nya `1AbCdEfGhIjKlMnOpQrSt`.
5. Simpan sebagai Secrets `GDRIVE_MUSIC_FOLDER_ID` dan `GDRIVE_OUTPUTS_FOLDER_ID`.

> Folder `shorts-sources` dari rencana lama **tidak dipakai lagi**. Latar sekarang dari Pexels, bukan dari Drive.

### 2.4 OAuth consent screen (YouTube)

1. `APIs & Services -> OAuth consent screen`.
2. User Type: **External** -> Create.
3. App name `shorts-bot`, User support email dan Developer email pakai Gmail-mu sendiri.
4. Scopes: tambahkan dua scope ini:
   - `https://www.googleapis.com/auth/youtube.upload` (upload Shorts)
   - `https://www.googleapis.com/auth/drive` (arsip hasil ke Drive pribadi)
5. **Test users**: tambahkan Gmail-mu sendiri.
6. Status biarkan **Testing** (cukup untuk akun pribadi, tidak perlu verifikasi Google).

### 2.5 OAuth client dan refresh token

1. `APIs & Services -> Credentials -> Create credentials -> OAuth client ID`.
2. Application type: **Desktop app**. Nama bebas, misalnya `shorts-bot-local`.
3. Simpan **Client ID** dan **Client secret** sebagai Secrets `YT_CLIENT_ID` dan `YT_CLIENT_SECRET`.
4. Di laptop:

   ```powershell
   copy .env.example .env
   notepad .env
   ```

   Isi `YT_CLIENT_ID` dan `YT_CLIENT_SECRET`, lalu:

   ```bash
   pip install requests
   python scripts/get_refresh_token.py
   ```

5. Browser terbuka. Kalau muncul "Google hasn't verified this app", klik **Advanced -> Go to shorts-bot (unsafe)**. Normal karena status Testing dan kamu test user.
6. Script menyimpan refresh token ke `.env` dan clipboard. Tempel sebagai Secret `YT_REFRESH_TOKEN`. Karena token dipakai untuk **YouTube + Drive**, consent harus disetujui ulang jika scope diubah.

PENTING: refresh token aplikasi berstatus **Testing** kedaluwarsa dalam **7 hari**. Kalau upload/arsip gagal dengan `invalid_grant`, ulangi langkah 2.5 dan ganti Secret `YT_REFRESH_TOKEN`.

---

## 3. Latar Pexels tanpa API key

Pexels saat ini **tidak memberikan API key baru**, jadi pipeline ini tidak memakai API sama sekali. Background diambil dari **URL MP4 langsung** `videos.pexels.com` yang sudah diverifikasi, dan daftarnya disimpan di `config/themes.json` pada `pexels_backgrounds`.

Field tiap entri:

| Field | Fungsi |
| --- | --- |
| `id` | ID video Pexels, dipakai untuk rotasi deterministik. |
| `description` | Dipakai prompt AI supaya teks relevan dengan visual. |
| `url` | Halaman video Pexels, masuk atribusi deskripsi. |
| `photographer` | Nama kreator, masuk atribusi deskripsi. |
| `file_url` | URL MP4 langsung yang diunduh runner. |

Cara menambah background baru:

1. Buka halaman video di Pexels, misalnya `https://www.pexels.com/video/30508832/`.
2. Ambil URL MP4 langsungnya (biasanya terlihat di network tab/devtools atau dari source video).
3. Cek cepat dengan `Invoke-WebRequest -Method Head <url>`; pastikan status `200` dan `Content-Type: video/mp4`.
4. Tambahkan objek baru ke array `pexels_backgrounds`. Tidak perlu ubah kode Python atau menambah Secret.

Lisensi Pexels memperbolehkan penggunaan komersial tanpa atribusi wajib, tapi **guideline meminta tautan ke Pexels dan kredit fotografer**. Itu sudah ditambahkan otomatis ke deskripsi YouTube oleh `scripts/plan.py`.

Pool yang terpakai sekarang:

| ID | Deskripsi | Fotografer | Halaman |
| --- | --- | --- | --- |
| `30508832` | Night city traffic from above with bokeh lights | David Saurik | https://www.pexels.com/video/night-city-traffic-from-above-with-bokeh-lights-30508832/ |
| `37779530` | Dynamic city night traffic timelapse | Sapol Churanon | https://www.pexels.com/video/dynamic-city-night-traffic-timelapse-37779530/ |

---

## 4. Musik freetouse.com

Dua track sudah kamu upload ke Drive `shorts-music` dan terdaftar di `config/themes.json`:

| Judul | Artis | Kategori | Durasi | Nama file | Halaman track |
| --- | --- | --- | --- | --- | --- |
| Unstoppable | Aylex | Inspiring, Storytelling | 3:08 | `unstoppable.mp3` | https://freetouse.com/music/aylex/unstoppable |
| Enlivening | Pufino | Inspiring, Piano | 2:32 | `enlivening.mp3` | https://freetouse.com/music/pufino/enlivening |

Track ketiga (**Cascade** oleh Alegend) tidak dipakai karena butuh subscription — tidak masalah, tidak ada biaya yang terlibat.

Skrip memilih salah satu dari pool di atas secara bergilir per tanggal, tapi **hanya yang file-nya benar-benar ada** di `work/music`. Jadi kalau suatu hari kamu tambah track, cukup:

1. Download MP3-nya, rename misalnya `cascade.mp3`, upload ke `shorts-music`.
2. Tambahkan objek `{ "file": ..., "title": ..., "url": ... }` ke array `music` di `config/themes.json`.
3. Commit file config tersebut. Tidak perlu ubah kode Python.

Judul + URL track otomatis masuk deskripsi YouTube, jadi atribusi tetap benar untuk track mana pun yang terpilih.

Free License freetouse **mewajibkan atribusi**, jadi judul + URL track otomatis masuk ke deskripsi YouTube. Lisensi ini juga melarang "Commercial Content" — aman untuk video YouTube biasa yang dimonetisasi asal atribusi benar, tapi baca kembali syaratnya di https://freetouse.com/license sebelum dipakai untuk iklan/konten sponsor.

Format deskripsi yang dipakai:

```text
Video latar: David Saurik / Pexels — https://www.pexels.com/video/.../
Musik: Unstoppable — https://freetouse.com/music/aylex/unstoppable (Free To Use)
```

PENTING: deskripsi YouTube **tidak mendukung markdown** `[nama](https://...)`, sehingga nama saja tidak bisa dijadikan tautan tersembunyi. URL polos akan otomatis jadi link yang bisa diklik — itulah sebabnya URL tetap ditampilkan setelah nama.

---

## 5. Konfigurasi tema (`config/themes.json`)

```json
{
  "defaults": {
    "duration_seconds": 30,
    "font_size": 72,
    "min_font_size": 34,
    "author_font_size": 48,
    "author_min_font_size": 30,
    "fade_in_min": 0.7,
    "fade_in_max": 1.4,
    "fade_in_per_word": 0.12,
    "line_gap": 0.7,
    "band_top": 620,
    "band_height": 680,
    "overlay_opacity": 0.55,
    "brightness": -0.18,
    "saturation": 0.75,
    "music_volume": 0.28
  },
  "themes": [
    {
      "id": "quotes",
      "niche": "Quotes inspiratif dan bermakna. Cocok untuk refleksi, motivasi, dan kebijaksanaan hidup.",
      "pexels_query": "cinematic background portrait bokeh",
      "pexels_backgrounds": [ { "...": "..." } ],
      "music": [ { "...": "..." } ]
    }
  ]
}
```

- `duration_seconds`: durasi video akhir.
- `font_size` / `min_font_size`: ukuran font maksimal/minimal untuk baris quote. Render otomatis mengecilkan font sampai teks muat di lebar 920 px.
- `author_font_size` / `author_min_font_size`: ukuran font untuk baris penulis (miring), biasanya lebih kecil dari quote.
- `fade_in_min` / `fade_in_max` / `fade_in_per_word`: durasi fade in dihitung dari jumlah kata, dibatasi 0,7–1,4 detik (`0,7 + 0,12 × kata`). **Tidak ada fade out** — teks bertahan setelah muncul.
- `line_gap`: **jeda tetap 0,7 detik** setelah fade in sebuah baris selesai; baris berikutnya (termasuk baris penulis) mulai fade in setelah itu.
- `band_top` / `band_height`: posisi dan tinggi shape hitam (koordinat 1080x1920). Layout baris dihitung dinamis; jika baris terakhir adalah penulis, posisinya ditempatkan di bawah blok quote.
- `overlay_opacity`: kegelapan shape hitam (`0.55` = 55%).
- `brightness` / `saturation`: menggelap dan meredupkan latar.
- `music_volume`: volume musik (0–1).
- `music`: array track. Skrip memilih satu per tanggal, tapi hanya dari file yang benar-benar tersedia di `work/music`.
- `pexels_backgrounds`: pool video Pexels berupa URL MP4 langsung. Skrip memilih satu per hari secara deterministik. Render tetap di-crop ke 1080x1920.

Render mendukung jumlah baris variabel (quote 1–3 baris + 1 baris penulis). Baris penulis menggunakan font miring (DejaVu Sans Oblique).

## 5.1 Cara menjalankan

- **Otomatis (jadwal)**: 06.00 & 18.00 WIB, mode `famous` (AI generate quotes terkenal, EN tetap EN, selain itu ID).
- **Manual famous**: Actions → **shorts-bot** → **Run workflow** → `mode = famous`.
- **Manual custom (bridge Telegram bot nanti)**: Actions → **Run workflow** → `mode = custom`, isi `quote_text` (pisahkan baris dengan `|` atau baris baru), opsional `quote_author` (default `dbcw`), `quote_language` (`auto/id/en`). Hasil: baris penulis `- dbcw -` (miring).

> Integrasi Telegram bot penuh belum diimplementasikan. Nanti bot dapat memicu workflow ini via GitHub REST API `workflow_dispatch` dengan input yang sama (`mode`, `quote_text`, `quote_author`, `quote_language`).

## 5.2 Log quotes terpakai

- File: `data/used_quotes.jsonl` (satu JSON per baris).
- Di-append oleh `scripts/plan.py` setiap run, lalu workflow melakukan auto-commit & push (`contents: write`).
- Dipakai sebagai konteks "hindari pengulangan" untuk mode `famous`.

---

## 6. Secrets dan Variables

### 6.1 Mulai dengan OpenRouter free tier

1. Daftar/login di https://openrouter.ai.
2. Buat API key di https://openrouter.ai/keys.
3. Masukkan sebagai **Repository Secret** `OPENROUTER_API_KEY` di repo `shorts-bot`.
4. Tidak perlu menaruhnya di `.env` lokal —yang membaca key adalah GitHub Actions, bukan laptopmu.
5. Biarkan `AI_PROVIDER = openrouter` dan `OPENROUTER_MODEL = inclusionai/ling-3.2-flash:free` (atau ganti Variable model ke `:free` lain).

Secrets (`Settings -> Secrets and variables -> Actions -> New repository secret`):

| Nama | Wajib | Keterangan |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | Ya* | API key OpenRouter. Pakai model `:free`, cukup untuk 2 video/hari. |
| `GEMINI_API_KEY` | Tidak | Fallback otomatis kalau OpenRouter error. |
| `DEEPSEEK_API_KEY` | Tidak | Fallback otomatis terakhir. |

\* **Cukup salah satu** dari tiga key AI di atas. Rekomendasi: isi `OPENROUTER_API_KEY` saja untuk mulai dengan free tier.
| `GDRIVE_SA_JSON` | Ya | Service account JSON (base64 satu baris). |
| `GDRIVE_MUSIC_FOLDER_ID` | Ya | ID folder berisi MP3. |
| `GDRIVE_OUTPUTS_FOLDER_ID` | Ya | ID folder arsip hasil. |
| `YT_CLIENT_ID` | Ya | OAuth client. |
| `YT_CLIENT_SECRET` | Ya | OAuth client. |
| `YT_REFRESH_TOKEN` | Ya | Perlu diganti tiap ~7 hari saat Testing. |

Variables (opsional, tab **Variables**):

| Nama | Default | Keterangan |
| --- | --- | --- |
| `AI_PROVIDER` | `openrouter` | Bisa diisi `gemini` atau `deepseek`. Urutan fallback: OpenRouter → Gemini → DeepSeek. |
| `OPENROUTER_MODEL` | `inclusionai/ling-3.2-flash:free` | Ganti ke model `:free` lain dari https://openrouter.ai/models bila perlu. |
| `YT_PRIVACY` | `public` | Pakai `unlisted` saat uji coba. |

---

## 7. Jalankan

1. Push semua file ke repo public akun sekunder.
2. Isi Secrets di atas.
3. Upload MP3 ke `shorts-music`, samakan nama filenya dengan `config/themes.json`.
4. Set Variable `YT_PRIVACY = unlisted` untuk uji coba pertama.
5. Buka **Actions -> shorts-bot -> Run workflow**.
6. Pantau log:
   - `Unduh musik dari Drive` harus menampilkan file MP3.
   - `Rencana` harus mencetak `[ok] tema: ... | Pexels video: ...`.
   - `Render` harus mencetak durasi dan ukuran file.
   - `Upload ke YouTube` harus mencetak video ID.
7. Kalau sudah oke, ganti `YT_PRIVACY` ke `public`; jadwal otomatis jalan dua kali sehari.

---

## 8. Biaya dan kuota

- GitHub Actions repo public: gratis unlimited, 4 core / 16 GB.
- Pexels: unduhan MP4 langsung, tanpa API key dan tanpa kuota API.
- Google Drive pribadi: gratis 15 GB.
- OpenRouter free tier: model `:free` Rp $0 untuk teks, text-only. Punya limit harian sendiri (biasanya puluhan request/hari), aman untuk 2 video/hari. Gemini/DeepSeek hanya fallback.
- YouTube Data API: `videos.insert` punya bucket sendiri **100 upload/hari**, biaya 1 kuota per call. Kuota lain 10.000 unit/hari. Aman.

---

## 9. Troubleshooting

- `rclone` gagal konek / `directory not found`: cek `GDRIVE_SA_JSON` (base64 satu baris tanpa spasi) dan pastikan `shorts-music` di-share ke email service account. Untuk service account, folder ID harus diset sebagai `root_folder_id` dan path-nya memakai `gdrive:` (bukan `gdrive:<id>`) — ini sudah diterapkan di workflow.
- `403 insufficientPermissions`: `shorts-music` belum di-share ke service account (Viewer) atau Drive API belum aktif.
- `storageQuotaExceeded`: service account dipakai untuk write. Arsip sekarang lewat `scripts/archive_drive.py` dengan OAuth user; jangan pakai `rclone copy` ke `shorts-outputs`.
- `Tidak ada file musik ...`: nama/Cek ekstensi MP3 dan `GDRIVE_MUSIC_FOLDER_ID`.
- `File musik tidak ditemukan: work/music/...`: nama file di Drive beda dengan `music.file` di `config/themes.json`.
- Unduhan Pexels gagal / `404`: `file_url` di `pexels_backgrounds` sudah kedaluwarsa atau salah. Buka halaman video, ambil URL MP4 terbaru, lalu commit ulang config.
- `Tidak ada 'pexels_backgrounds'`: config belum punya pool background; tambahkan entri seperti di bagian 3.
- OpenRouter `401`: Secret `OPENROUTER_API_KEY` salah/belum terisi. Buat key di https://openrouter.ai/keys.
- OpenRouter `429` / `402`: limit free tier tercapai atau model bukan `:free`. Ganti `OPENROUTER_MODEL` ke model `:free` lain, atau tunggu reset harian.
- `Semua provider AI gagal`: semua key AI tidak ada/salah. Isi minimal `OPENROUTER_API_KEY`.
- `invalid_grant` saat upload: refresh token kedaluwarsa (7 hari). Ulangi langkah 2.5.
- `quotaExceeded`: cek halaman Quotas di Google Cloud.
- Hasil video terlalu besar: turunkan `-crf 23` ke `-crf 26` di `scripts/render.py`.
- Scheduled workflow berhenti setelah 60 hari tanpa aktivitas: GitHub menonaktifkan cron pada repo dormant. Cukup buat commit kecil atau jalankan `Run workflow` sekali.

---

## 10. Risiko konten

YouTube punya kebijakan **reused content**. Video dengan latar yang persis sama dan hanya beda teks berisiko dianggap repetitif. Mitigasi yang sudah disiapkan:

- Gunakan **beberapa entri `pexels_backgrounds`** per tema (mulai 2, tambahkan sampai 3–5) supaya latar berganti.
- Bedakan judul/caption tiap run lewat AI.
- Hindari mengupload lebih dari 2 video/hari dengan tema identik.
