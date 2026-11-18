# shorts-bot

Automasi Shorts Bahasa Indonesia dengan konsep **teks dulu, gambar belakang**. Latar video diambil dari Pexels, digelap dan diberi shape hitam supaya teks terbaca, lalu 3 baris teks muncul bertahap. Musik dari freetouse.com. Semua proses di GitHub Actions (repo public = gratis unlimited), hasil diarsipkan ke Google Drive, lalu di-upload ke YouTube Shorts.

```
Pexels MP4 langsung --latar--> Runner GitHub (4 core / 16 GB)
Drive /music --rclone-->  |
                          +-- AI: 3 baris teks + judul + caption (TEKS SAJA, tanpa gambar)
                          +-- ffmpeg: gelap + black band + teks bertahap + musik
                          |
                          +--OAuth--> Drive /outputs/<tanggal>  (arsip + caption.txt)
                          +--API----> YouTube Shorts
```

Jadwal default: **06.00 dan 18.00 WIB** (cron `0 23 * * *` dan `0 11 * * *` dalam UTC).

## Catatan konsep soal token

- **Mengulang video latar dan backsound TIDAK menghemat token AI.** Token dibayar dari teks yang dikirim, bukan dari file video/musik.
- Yang benar-benar menghemat token adalah **tidak mengirim thumbnail/gambar ke AI**. Rencana lama mengirim 8 thumbnail per run; rencana ini **nol gambar**, jadi biaya AI turun drastis.
- Supaya konten tidak terasa statis, tiap tema punya **pool kecil** `pexels_backgrounds` berisi URL MP4 langsung dari Pexels. Skrip memilih satu secara deterministik berdasarkan tanggal, jadi latar bisa berulang tapi tidak selalu sama persis.

---

## 1. Repo GitHub (akun sekunder)

1. Buat repo **public**, misalnya `shorts-bot`.
2. `Settings -> Actions -> General -> Workflow permissions` -> **Read repository contents and packages**.
3. Jangan pasang kartu pembayaran di akun sekunder. Repo public = Actions gratis unlimited, 4 core / 16 GB.
4. File `.env`, `sa.json`, folder `work/`, dan `out/` sudah masuk `.gitignore`. Jangan pernah di-commit.

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

---

## 5. Konfigurasi tema (`config/themes.json`)

```json
{
  "defaults": {
    "duration_seconds": 30,
    "lines": 3,
    "font_size": 72,
    "band_top": 680,
    "band_height": 560,
    "overlay_opacity": 0.55,
    "brightness": -0.18,
    "saturation": 0.75,
    "music_volume": 0.28
  },
  "themes": [
    {
      "id": "motivasi-malam",
      "niche": "Motivasi produktivitas dan semangat kerja, Bahasa Indonesia. Nada optimistis, singkat, dan konkret.",
      "pexels_query": "city night lights timelapse portrait",
      "pexels_backgrounds": [
        {
          "id": 30508832,
          "description": "night city traffic from above with bokeh lights",
          "url": "https://www.pexels.com/video/night-city-traffic-from-above-with-bokeh-lights-30508832/",
          "photographer": "David Saurik",
          "file_url": "https://videos.pexels.com/video-files/30508832/13071300_1440_2560_30fps.mp4"
        },
        {
          "id": 37779530,
          "description": "dynamic city night traffic timelapse",
          "url": "https://www.pexels.com/video/dynamic-city-night-traffic-timelapse-37779530/",
          "photographer": "Sapol Churanon",
          "file_url": "https://videos.pexels.com/video-files/37779530/16024710_1440_2560_30fps.mp4"
        }
      ],
      "music": [
        {
          "file": "unstoppable.mp3",
          "title": "Unstoppable",
          "url": "https://freetouse.com/music/aylex/unstoppable"
        },
        {
          "file": "enlivening.mp3",
          "title": "Enlivening",
          "url": "https://freetouse.com/music/pufino/enlivening"
        }
      ]
    }
  ]
}
```

- `duration_seconds`: durasi video akhir.
- `lines`: jumlah baris teks bertahap (default 3; render mendukung maksimal 3).
- `band_top` / `band_height`: posisi dan tinggi shape hitam (koordinat 1080x1920).
- `overlay_opacity`: kegelapan shape hitam (`0.55` = 55%).
- `brightness` / `saturation`: menggelap dan meredupkan latar.
- `music_volume`: volume musik (0–1).
- `music`: array track. Skrip memilih satu per tanggal, tapi hanya dari file yang benar-benar tersedia di `work/music`.
- `pexels_backgrounds`: pool video Pexels berupa URL MP4 langsung. Skrip memilih satu per hari secara deterministik (berdasarkan tanggal), jadi latar bergilir tapi bisa diprediksi. Semua video di pool sudah portrait 9:16; render tetap di-crop ke 1080x1920.

Pool yang terisi sekarang adalah video **kota malam / lalu lintas bokeh** portrait 9:16, 30 fps. Cara menambah: lihat bagian **3. Latar Pexels tanpa API key**. Field `pexels_query` tetap dipakai sebagai fallback deskripsi untuk prompt AI.

Karena hanya ada **satu tema**, prompt AI jadi lebih pendek dan biaya token makin kecil.

---

## 6. Secrets dan Variables

Secrets (`Settings -> Secrets and variables -> Actions -> New repository secret`):

| Nama | Wajib | Keterangan |
| --- | --- | --- |
| `GEMINI_API_KEY` | Ya | Google AI Studio API key. |
| `DEEPSEEK_API_KEY` | Tidak | Fallback otomatis kalau Gemini error. |
| `GDRIVE_SA_JSON` | Ya | Service account JSON (base64 satu baris). |
| `GDRIVE_MUSIC_FOLDER_ID` | Ya | ID folder berisi MP3. |
| `GDRIVE_OUTPUTS_FOLDER_ID` | Ya | ID folder arsip hasil. |
| `YT_CLIENT_ID` | Ya | OAuth client. |
| `YT_CLIENT_SECRET` | Ya | OAuth client. |
| `YT_REFRESH_TOKEN` | Ya | Perlu diganti tiap ~7 hari saat Testing. |

Variables (opsional, tab **Variables**):

| Nama | Default | Keterangan |
| --- | --- | --- |
| `AI_PROVIDER` | `gemini` | Isi `deepseek` untuk pakai DeepSeek sebagai utama. |
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
- Gemini 3.5 Flash-Lite: text-only, biaya sangat kecil (kemungkinan besar $0 untuk 2 video/hari).
- YouTube Data API: `videos.insert` punya bucket sendiri **100 upload/hari**, biaya 1 kuota per call. Kuota lain 10.000 unit/hari. Aman.

---

## 9. Troubleshooting

- `rclone` gagal konek: cek `GDRIVE_SA_JSON` (base64 satu baris tanpa spasi) dan pastikan folder di-share ke email service account.
- `403 insufficientPermissions`: `shorts-music` belum di-share ke service account (Viewer) atau Drive API belum aktif.
- `storageQuotaExceeded`: service account dipakai untuk write. Arsip sekarang lewat `scripts/archive_drive.py` dengan OAuth user; jangan pakai `rclone copy` ke `shorts-outputs`.
- `Tidak ada file musik ...`: nama/Cek ekstensi MP3 dan `GDRIVE_MUSIC_FOLDER_ID`.
- `File musik tidak ditemukan: work/music/...`: nama file di Drive beda dengan `music.file` di `config/themes.json`.
- Unduhan Pexels gagal / `404`: `file_url` di `pexels_backgrounds` sudah kedaluwarsa atau salah. Buka halaman video, ambil URL MP4 terbaru, lalu commit ulang config.
- `Tidak ada 'pexels_backgrounds'`: config belum punya pool background; tambahkan entri seperti di bagian 3.
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
