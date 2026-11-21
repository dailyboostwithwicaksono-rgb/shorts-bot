# shorts-bot

Automasi YouTube Shorts bertema **quotes**: teks quote di atas latar video dari **Pixabay** (dipilih relevan via kata kunci AI, filter metadata oleh kode) dengan gaya visual konsisten (grayscale + overlay + band ber-gradasi), musik latar dari **Freetouse API** (non-premium, tema calm/motivasi), arsip ke Google Drive, lalu upload ke YouTube Shorts. Proses utama berjalan di **GitHub Actions** (bisa juga dijalankan **lokal**, lihat [docs/RUNNING_LOCAL.md](docs/RUNNING_LOCAL.md)).

## Ringkasan
- **Latar**: video dari **Pixabay Video API** (`PIXABAY_API_KEY`). AI (teks saja, 1 langkah) menghasilkan **1–3 kata kunci** dari isi quote → kode mencari & memfilter metadata (tanpa animasi, durasi ≥ quote dengan pelonggaran bertahap, kualitas progresif **tanpa upscale** F1 → F2 → semua, prefer `large`) → ambil hingga 3 kandidat → **pilih 1 acak (kode)**. Jika kosong, fallback ke cache keberhasilan di `data/pixabay_cache.json` (di-commit). Pexels dinonaktifkan.
- **Musik**: dari **Freetouse Public API** (`https://api.freetouse.com/v3`, tanpa API key). Dipilih per run: hanya track **non-premium/usable** (`is_premium == false`, `status == 1`, file MP3 tersedia), dengan query/tema yang cocok untuk short motivasi/calm (mis. inspirational, motivational, calm, uplifting, ambient, hopeful, peaceful, piano, cinematic, nature) + penilaian kecocokan tag/judul, dan durasi memadai (prefer `>= 60s` dan `>= durasi video`, dengan pelonggaran bertahap). Diunduh saat proses; jika API gagal, fallback ke file musik lokal bila tersedia. Atribusi (judul, artis, URL track best-effort) masuk deskripsi.
- **Render**: 1080×1920, 30 fps, durasi **per quote** (detik), ffmpeg + Pillow. Latar: **grayscale** + **overlay hitam penuh ~30%** + **dark band dengan tepi atas/bawah ber-gradasi (feather)**. Durasi sumber dideteksi (`ffprobe`): jika lebih pendek dari target → **diperlambat (setpts)** agar pas; jika lebih panjang → dipotong.
- **Arsip**: `out/*` ke Drive `shorts-outputs/<tanggal>` via OAuth user.
- **Upload**: YouTube Shorts via OAuth user.
- **Log & metadata (di-commit)**: `data/used_quotes.jsonl`, `data/pixabay_cache.json`, `data/used_videos.jsonl`, `data/used_music.jsonl` di-update dan **auto-commit** oleh workflow (menyimpan metadata semua video/musik yang pernah dipakai).

**Penyimpanan/media (GitHub Actions):** file video & audio latar/musik **diunduh saat run** ke folder kerja (`work/`) untuk dirender, **tidak di-commit** (ephemeral; `work/`, `out/`, `render_plan.json` di-`.gitignore`) agar tidak menambah storage repo. Hanya log/metadata di atas yang disimpan di repo; artifact run hanya menyimpan log kecil singkat.

Jadwal: **03.00 dan 18.00 WIB** (cron `0 20 * * *` dan `0 11 * * *` UTC, `workflow_dispatch` tersedia). Jadwal GitHub Actions bisa tertunda.

## Mode konten
- **`list` (default, jadwal/manual)**: baca `data/quotes.json`, pilih berurutan berdasarkan `id` menaik (entri pertama yang belum tercatat di `data/used_quotes.jsonl`). Jika semua sudah terpakai → **loop dari awal**.
- **`famous` (AI)**: kurasi quotes terkenal via AI (EN tetap EN, selain itu ID), menghindari pengulangan berdasarkan log. Metadata (judul/caption/hashtag) dibantu AI.
- **`custom` (manual / bridge Telegram bot nanti)**: jalankan **Actions → shorts-bot → Run workflow** dengan `mode=custom`, isi `quote_text` (pisah baris dengan `|` atau baris baru), opsional `quote_author` (default `dbcw`, ditampilkan sebagai `- dbcw -`), `quote_language` (`auto/id/en`). Integrasi Telegram bot penuh belum dibuat; nanti dapat memicu `workflow_dispatch` (GitHub API) dengan input yang sama.

## Tipografi & tampilan
- Kanvas 1080×1920, teks rata tengah, **huruf kecil semua** (dinormalisasi).
- **Latar**: dikonversi **grayscale** (saturasi 0) + **overlay hitam penuh ~30%** untuk konsistensi; **dark band** area teks dipertahankan dengan tepi **atas & bawah ber-gradasi (feather, solid → transparan)** agar teks tetap terbaca.
- Font **Montserrat** (OFL, dibundle di `assets/fonts/`):
  - Quote: **Montserrat Light Italic 51pt**, `#FFFFFF`
  - Penekanan (emphasis): **Montserrat SemiBold Italic 51pt**, `#FFFFFF` (inline, ukuran sama)
  - Nama tokoh: **Montserrat Italic 28pt**, `#DDDDDD`, format `- nama -`
  - Tanpa author/sumber terverifikasi: **garis pendek 100 px × 2 px**, `#DDDDDD` (di posisi author)
- Line spacing **1,3×**.
- **Progressive fade-in per baris** (quote lalu author/garis), baris tetap tampil/bertumpuk: durasi fade `clamp(0,7 + 0,12 × kata, 0,7, 1,4)` detik, **jeda tetap 0,7 detik** setelah fade-in tiap baris sebelum baris berikutnya, tanpa fade-out teks.
- Ukuran quote 51pt (fix) dengan fallback **shrink** hanya jika baris terpaksa melebihi lebar aman.

## Format `data/quotes.json`
```json
{
  "quotes": [
    {
      "id": 3,
      "lines": [
        "kamu tidak harus menjadi",
        "sempurna untuk memulai,",
        "tetapi kamu harus memulai",
        "untuk menjadi lebih baik."
      ],
      "emphasis": ["tidak harus", "memulai", "lebih baik"],
      "author": "anonim",
      "duration": 20
    }
  ]
}
```
- `id`: nomor/indeks unik, dipakai untuk urutan & pelacakan.
- `lines`: 1–5 baris (baris sudah ditentukan).
- `emphasis`: frasa penekanan, **berurutan** — tiap frasa dipasangkan ke kemunculan berikutnya yang belum terpakai (scan baris 1→akhir, kiri→kanan, case-insensitive, non-overlapping). Jika tidak ditemukan, dilewati.
- `author`: nama tokoh; kosong/tidak ada → garis fallback. Tampil sebagai `- nama -`.
- `duration`: durasi video (detik).

`data/used_quotes.jsonl` berisi riwayat pemakaian (termasuk `id` untuk mode `list`) dan dipakai agar pilihan berurutan/tidak terulang.

## Konfigurasi (`config/themes.json`)
- `defaults`: mode/file default, path log/metadata (`quotes_file`, `used_quotes_file`, `pixabay_cache_file`, `used_videos_file`, `used_music_file`), tipografi (`quote_font_size`, `author_font_size`, `line_spacing`, `max_text_width`, warna, ukuran garis), timing (`fade_in_*`, `line_gap`), layout/gaya visual (`band_top`, `band_height`, `overlay_opacity`, `full_overlay_opacity`, `band_feather`, `brightness`, `saturation`, `music_volume`).
- `themes[].pixabay_query`: kueri/cadangan untuk pencarian latar Pixabay (keyword utama dihasilkan per quote).
- `themes[].music`: (opsional, fallback) daftar musik lokal (`file`, `title`, `url`) — dipakai hanya jika pengambilan dari Freetouse API gagal dan file tersedia di `work/music/`. Alur utama mengambil musik dari Freetouse API per run.

## Latar Pixabay (API)
Latar dipilih otomatis dari **Pixabay Video API** (`PIXABAY_API_KEY`) berdasarkan kata kunci yang dibuat dari quote, lalu difilter oleh kode (tanpa animasi, durasi/kualitas progresif, pilih acak 1 dari kandidat). Entri keberhasilan disimpan di `data/pixabay_cache.json` (di-commit) sebagai fallback bila pencarian berikutnya kosong/gagal. Atribusi (user/URL Pixabay) otomatis masuk deskripsi. Patuhi ketentuan lisensi Pixabay.

## Distribusi & multi-platform (Fase 3–4)
- **Kontrak konten:** distribusi membaca konten kanonik dari artefak render (`out/manifest.json`, `out/final.mp4`, `out/caption.txt`).
- **Arsip:** `scripts/archive_drive.py` tetap mengarsipkan `out/*` ke Drive (target Google terpisah).
- **Publish (dispatcher):** `scripts/publish.py` mem-publish ke target aktif via `PUBLISH_TARGETS` (default: `youtube`, perilaku sama seperti sebelumnya). Opsi: `PUBLISH_DRY_RUN=1` (formatter/validasi tanpa upload nyata), `PUBLISH_FAIL_FAST` (default `1`, gagal cepat; `0` untuk lanjut parsial) dengan ringkasan hasil per target.
- **Platform tambahan (kerangka):** formatter + stub/dry-run untuk **TikTok, Meta, X** tersedia (`PUBLISH_TARGETS=youtube,tiktok,meta,x`). Publish **nyata** ke platform tersebut bertahap dan memerlukan akun/app, izin/API, kredensial, serta implementasi API masing-masing; tanpa itu gunakan dry-run atau target akan gagal/ditolak dengan pesan jelas (tidak ada publish palsu).
- **Secrets/env per platform (opsional, saat diaktifkan):** TikTok `TIKTOK_ACCESS_TOKEN`; Meta `META_ACCESS_TOKEN`, `META_IG_USER_ID`; X `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`. YouTube/Drive tetap memakai kredensial Google (`YT_*`, `GDRIVE_OUTPUTS_FOLDER_ID`).

## Musik Freetouse (API)
Musik diambil otomatis dari **Freetouse Public API** (tanpa API key). Sistem memilih track **non-premium** yang dapat dipakai (`is_premium == false`, `status == 1`, MP3 ada) dengan tema/mood cocok untuk short motivasi/calm (inspirational/motivational/calm/uplifting/ambient/hopeful/peaceful/piano/cinematic/nature, dll.) dan durasi memadai (prefer `>= 60s` dan `>= durasi video`). Atribusi judul, artis, dan URL track (best-effort) otomatis masuk deskripsi. Metadata setiap musik yang dipakai dicatat di `data/used_music.jsonl`. Cek syarat lisensi di https://freetouse.com/license.

## Setup (ringkas, GitHub Actions)
1. **Repo** public, akun sekunder. `Settings → Actions → General → Workflow permissions` = **Read and write** (untuk auto-commit log/metadata). Jangan commit `.env`, `work/`, `out/`.
2. **Google Cloud** (untuk arsip Drive & upload YouTube): aktifkan Google Drive API & YouTube Data API v3. Buat OAuth client Desktop + consent screen (scope `drive` & `youtube.upload`).
3. **Folder Drive (arsip output)**: `shorts-outputs` → simpan ID sebagai `GDRIVE_OUTPUTS_FOLDER_ID` (ditulis via OAuth user).
4. **Refresh token OAuth**: isi `YT_CLIENT_ID`/`YT_CLIENT_SECRET` di `.env` lokal lalu `python scripts/get_refresh_token.py`, simpan token ke secret `YT_REFRESH_TOKEN`.
5. **API key layanan**:
   - **Pixabay**: `PIXABAY_API_KEY` (latar video).
   - **AI** (untuk keyword latar & mode `famous`/metadata custom): `OPENROUTER_API_KEY` (model `:free`), opsional `GEMINI_API_KEY`/`DEEPSEEK_API_KEY` sebagai fallback.
   - **Musik**: tidak perlu key/Drive (diambil dari Freetouse Public API per run).

## Mengubah OAuth app dari Testing ke Production
Saat status **Testing**, refresh token bisa kedaluwarsa ~7 hari (`invalid_grant`). Memindahkan ke **Production** (di luar Testing) menghilangkan batas kedaluwarsa 7 hari tersebut (token tetap bisa invalid jika dicabut/alasan keamanan lain).

1. Buka **Google Cloud Console → APIs & Services → OAuth consent screen** (Google Auth Platform → Branding/Audience).
2. **Lengkapi Branding** (tombol Publish nonaktif jika ada yang kurang). Wajib umumnya:
   - **App name** dan **User support email**.
   - **Application home page** (URL `https` valid), mis. `https://github.com/dailyboostwithwicaksono-rgb/shorts-bot`.
   - **Application privacy policy link** (URL `https` valid, kolom terpisah), mis. `https://github.com/dailyboostwithwicaksono-rgb/shorts-bot/blob/main/PRIVACY.md` (tersedia di repo).
   - **Authorized domains**: tambahkan domain dari URL di atas (mis. `github.com`) lalu simpan.
   - **Developer contact information** (email). Simpan semua perubahan.
3. Pastikan **Audience/Data access** (scope `youtube.upload`, `drive`) sesuai. Untuk Gmail pribadi tipe user adalah **External** (Internal hanya Google Workspace).
4. Klik **Publish app / In production**.
5. **Buat refresh token baru** dan perbarui kredensial:
   - Jalankan `python scripts/get_refresh_token.py` (login & setujui izin; jika ada peringatan “unverified app”, lanjutkan untuk akun sendiri).
   - Update secret GitHub **`YT_REFRESH_TOKEN`** dengan token baru.
6. Uji workflow (arsip Drive & upload YouTube) memastikan tidak ada `invalid_grant`.

**Catatan penting:**
- Scope `youtube.upload` dan `drive` bersifat sensitif/terbatas. App Production dengan scope tersebut dapat memerlukan **verifikasi app** oleh Google sesuai kebijakan; untuk penggunaan pribadi 1 akun sering kali tetap dapat berjalan, namun persyaratan/verifikasi bisa menjadi kendala.
- **OAuth user cap**: untuk app yang meminta scope sensitif/terbatas yang belum disetujui, jumlah pengguna yang bisa memberi izin dibatasi sepanjang masa proyek (tidak bisa di-reset). Untuk pemakaian **hanya oleh akunmu sendiri**, ini praktis tidak masalah — jangan memberi akses ke pengguna lain. Layar “unverified app” dapat muncul bila scope belum disetujui.

## Secrets & Variables (GitHub Actions)
Secrets: `OPENROUTER_API_KEY` (atau Gemini/DeepSeek), `PIXABAY_API_KEY`, `GDRIVE_OUTPUTS_FOLDER_ID`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

Variables (opsional): `AI_PROVIDER` (`openrouter`), `OPENROUTER_MODEL` (`inclusionai/ling-3.2-flash:free`), `YT_PRIVACY` (`public`/`unlisted`), `PUBLISH_TARGETS` (default `youtube`), `PUBLISH_DRY_RUN` (default `0`), `PUBLISH_FAIL_FAST` (default `1`).

Secrets opsional (multi-platform, saat target diaktifkan & implementasi API siap): TikTok `TIKTOK_ACCESS_TOKEN`; Meta `META_ACCESS_TOKEN`, `META_IG_USER_ID`; X `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`.

> Catatan: musik diambil dari Freetouse API (tanpa key/Drive/rclone), sehingga `GDRIVE_SA_JSON` dan `GDRIVE_MUSIC_FOLDER_ID` tidak diperlukan untuk alur musik saat ini.

## Menjalankan di GitHub Actions
- Otomatis: jadwal 03.00 & 18.00 WIB (`mode=list`).
- Manual: **Actions → shorts-bot → Run workflow** (pilih `mode`: `list`/`famous`/`custom`).

## Menjalankan di lokal (detail, bertahap)
Panduan lengkap (untuk pemula, termasuk instalasi ffmpeg, env, penjadwalan lokal, dan **cek krusial saat error/gagal**): **[docs/RUNNING_LOCAL.md](docs/RUNNING_LOCAL.md)**.

Ringkas: pasang dependensi Python & ffmpeg → set `PIXABAY_API_KEY` (dan AI key jika perlu) dengan internet aktif → `python scripts/plan.py` → `python scripts/render.py` → ambil `out/final.mp4` + `out/caption.txt` (judul/deskripsi siap tempel) untuk **upload manual** ke YouTube. Latar dari Pixabay API (cache fallback di `data/pixabay_cache.json`); musik diambil otomatis dari Freetouse API (non-premium, tema calm/motivasi, durasi memadai) dan diunduh saat run. File media tidak di-commit; metadata pemakaian tersimpan di `data/used_videos.jsonl` dan `data/used_music.jsonl`.

## Maintenance
- **Token OAuth**: jika app **Testing** → refresh token kedaluwarsa ~7 hari (`invalid_grant`), regenerate & update `YT_REFRESH_TOKEN`. Jika sudah **Production** → tidak ada kedaluwarsa 7 hari, namun token tetap bisa invalid (dicabut/alasan keamanan) — siapkan cara regenerate. Untuk alur lokal *upload manual* (tanpa arsip/upload otomatis), OAuth user tidak diperlukan.
- **Actions (1–2×/minggu)**: cek run terjadwal sukses; jadwal bisa telat. Jika gagal, periksa langkah merah (Pixabay/Freetouse API atau rate limit/koneksi, AI, token/quota YouTube/Drive arsip, commit log/metadata). Workflow butuh **Read and write permissions** untuk auto-commit log/metadata.
- **Stok quotes**: pastikan `data/quotes.json` cukup; mode `list` loop jika habis, namun tetap baik menambah variasi.
- **Cache latar & metadata**: `data/pixabay_cache.json` membantu fallback latar; metadata pemakaian video/musik tersimpan di `data/used_videos.jsonl` dan `data/used_music.jsonl` (di-commit). Arsip output di Drive menambah kuota Drive (file media tidak di-commit ke repo).
- **YouTube API quota**: 2 upload/hari umumnya aman; cek jika menaikkan frekuensi.
- **AI**: model `:free` dapat berubah ketersediaan/rate limit; ganti `OPENROUTER_MODEL` bila perlu. Keyword latar punya fallback heuristik, mode `famous/custom` butuh AI.
- **Repo dormant**: jadwal dapat dinonaktifkan jika repo lama tidak aktif — jalankan manual/commit kecil untuk mengaktifkan kembali.

## Troubleshooting singkat
- `invalid_grant`: token OAuth kedaluwarsa (Testing) atau dicabut → regenerate `YT_REFRESH_TOKEN` (dan pastikan app/consent sesuai).
- Pixabay gagal/kosong: cek `PIXABAY_API_KEY`, kuota/rate limit, koneksi internet, atau cache `data/pixabay_cache.json` (fallback bila tersedia).
- Musik Freetouse gagal/kosong: cek koneksi internet ke `api.freetouse.com` (tidak perlu key). Sistem memilih track non-premium/usable bertema calm/motivasi; jika API gagal dan tidak ada file lokal fallback, proses berhenti.
- AI gagal/rate limit: cek key, model `:free`, atau fallback provider (mode `list` tidak butuh AI; keyword latar punya fallback heuristik).
- Commit log/metadata gagal: cek Workflow permissions (Read and write).
- `quotaExceeded` (YouTube): cek kuota di Google Cloud Console.
- Error lokal (ffmpeg, dependensi, disk, internet, dll.): lihat bagian **“Cek krusial saat error atau gagal”** di [docs/RUNNING_LOCAL.md](docs/RUNNING_LOCAL.md).
