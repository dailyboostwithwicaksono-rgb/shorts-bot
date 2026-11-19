# shorts-bot

Automasi YouTube Shorts bertema **quotes**: teks quote di atas latar Pexels (digelap + dark band), musik dari freetouse.com, arsip ke Google Drive, lalu upload ke YouTube Shorts. Proses berjalan di GitHub Actions.

## Ringkasan
- **Latar**: URL MP4 langsung Pexels (`config/themes.json`), dipilih **acak per run**.
- **Musik**: dari folder Drive `shorts-music` (rclone + service account), dipilih **acak per run**.
- **Render**: 1080x1920, 30 fps, durasi **per quote** (detik), ffmpeg + Pillow (overlay teks).
- **Arsip**: `out/*` ke Drive `shorts-outputs/<tanggal>` via OAuth user.
- **Upload**: YouTube Shorts via OAuth user.
- **Log**: `data/used_quotes.jsonl` di-append tiap run dan **auto-commit** oleh workflow.

Jadwal: **06.00 dan 18.00 WIB** (cron `0 23 * * *` dan `0 11 * * *` UTC, `workflow_dispatch` tersedia). Jadwal GitHub Actions bisa tertunda.

## Mode konten
- **`list` (default, jadwal/manual)**: baca `data/quotes.json`, pilih berurutan berdasarkan `id` menaik (entri pertama yang belum tercatat di `data/used_quotes.jsonl`). Jika semua sudah terpakai → **loop dari awal**.
- **`famous` (AI)**: kurasi quotes terkenal via AI (EN tetap EN, selain itu ID), menghindari pengulangan berdasarkan log. Metadata (judul/caption/hashtag) dibantu AI.
- **`custom` (manual / bridge Telegram bot nanti)**: jalankan **Actions → shorts-bot → Run workflow** dengan `mode=custom`, isi `quote_text` (pisah baris dengan `|` atau baris baru), opsional `quote_author` (default `dbcw`, ditampilkan sebagai `- dbcw -`), `quote_language` (`auto/id/en`). Integrasi Telegram bot penuh belum dibuat; nanti dapat memicu `workflow_dispatch` (GitHub API) dengan input yang sama.

## Tipografi & tampilan
- Kanvas 1080×1920, teks rata tengah, **huruf kecil semua** (dinormalisasi).
- Font **Montserrat** (OFL, dibundle di `assets/fonts/`):
  - Quote: **Montserrat Light Italic 51pt**, `#FFFFFF`
  - Penekanan (emphasis): **Montserrat SemiBold Italic 51pt**, `#FFFFFF` (inline, ukuran sama)
  - Nama tokoh: **Montserrat Italic 28pt**, `#DDDDDD`, format `- nama -`
  - Tanpa author/sumber terverifikasi: **garis pendek 100 px × 2 px**, `#DDDDDD` (di posisi author)
- Line spacing **1,3×**. Latar digelapkan + **dark band** (tanpa panel blur).
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
- `defaults`: mode/file default, tipografi (`quote_font_size`, `author_font_size`, `line_spacing`, `max_text_width`, warna, ukuran garis), timing (`fade_in_*`, `line_gap`), layout band (`band_top`, `band_height`, `overlay_opacity`, `brightness`, `saturation`, `music_volume`).
- `themes[].pexels_backgrounds`: pool latar (MP4 langsung `file_url`, + `id/url/photographer/description`).
- `themes[].music`: pool musik (`file`, `title`, `url`) — file harus ada di `work/music` (diunduh dari Drive).

## Latar Pexels (tanpa API key)
Tambah background: ambil `file_url` MP4 langsung dari Pexels, verifikasi (200, `video/mp4`), tambahkan entri ke `pexels_backgrounds` dan commit. Atribusi fotografer/tautan Pexels otomatis masuk deskripsi. Lisensi Pexels mengizinkan penggunaan komersial; atribusi tetap dicantumkan sesuai guideline.

## Musik freetouse.com
Lisensi Free To Use mewajibkan atribusi; judul + URL track otomatis masuk deskripsi YouTube (URL polos/clickable). Tambah track: upload ke `shorts-music`, daftarkan di `config/themes.json`. Cek syarat lisensi di https://freetouse.com/license.

## Setup (ringkas)
1. **Repo** public, akun sekunder. `Settings → Actions → General → Workflow permissions` = **Read and write** (untuk auto-commit log). Jangan commit `.env`, `sa.json`, `work/`, `out/`.
2. **Google Cloud**: aktifkan Google Drive API & YouTube Data API v3. Buat Service Account (JSON → base64 sebagai `GDRIVE_SA_JSON`) untuk **baca musik** dari Drive (share folder musik ke SA sebagai Viewer). Buat OAuth client Desktop + consent screen (scope `drive` & `youtube.upload`, test user = akunmu) untuk **arsip Drive & upload YouTube**.
3. **Folder Drive**: `shorts-music` (berisi mp3) → share ke SA (Viewer), simpan ID sebagai `GDRIVE_MUSIC_FOLDER_ID`. `shorts-outputs` → ID sebagai `GDRIVE_OUTPUTS_FOLDER_ID` (ditulis via OAuth user, SA tidak punya kuota tulis Drive pribadi).
4. **Refresh token OAuth**: isi `YT_CLIENT_ID`/`YT_CLIENT_SECRET` di `.env` lokal lalu `python scripts/get_refresh_token.py`, simpan token ke secret `YT_REFRESH_TOKEN`.
5. **AI** (untuk mode `famous`/metadata custom): isi `OPENROUTER_API_KEY` (model `:free`), opsional `GEMINI_API_KEY`/`DEEPSEEK_API_KEY` sebagai fallback.

## Secrets & Variables
Secrets: `OPENROUTER_API_KEY` (atau Gemini/DeepSeek), `GDRIVE_SA_JSON`, `GDRIVE_MUSIC_FOLDER_ID`, `GDRIVE_OUTPUTS_FOLDER_ID`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

Variables (opsional): `AI_PROVIDER` (`openrouter`), `OPENROUTER_MODEL` (`inclusionai/ling-3.2-flash:free`), `YT_PRIVACY` (`public`/`unlisted`).

## Menjalankan
- Otomatis: jadwal 06.00 & 18.00 WIB (`mode=list`).
- Manual: Actions → **shorts-bot** → **Run workflow** (pilih `mode`: `list`/`famous`/`custom`).

## Maintenance
- **Token OAuth (penting, mingguan)**: app berstatus **Testing** → refresh token bisa kedaluwarsa ~7 hari. Gejala: `invalid_grant` saat arsip/upload. Solusi: jalankan ulang `scripts/get_refresh_token.py`, update secret `YT_REFRESH_TOKEN`.
- **Actions (1–2×/minggu)**: cek run 06.00 & 18.00 WIB sukses; jadwal bisa telat. Jika gagal, periksa langkah merah (AI/rate limit, token/quota YouTube, rclone/Drive, commit log). Workflow butuh **Read and write permissions** untuk auto-commit log.
- **Stok quotes**: pastikan `data/quotes.json` masih cukup; mode `list` akan loop jika habis, tapi tetap baik menambah entri/variasi.
- **Pool media & kuota Drive**: tambah variasi background/musik agar tidak repetitif; arsip output menambah pemakaian kuota Drive akun OAuth.
- **YouTube API quota**: 2 upload/hari biasanya aman; cek jika menaikkan frekuensi.
- **AI**: model `:free` bisa berubah ketersediaan/rate limit; ganti `OPENROUTER_MODEL` bila perlu.
- **Repo dormant**: workflow schedule dapat dinonaktifkan jika repo lama tidak aktif — jalankan manual/commit kecil untuk mengaktifkan kembali.

## Troubleshooting singkat
- `invalid_grant`: token OAuth kedaluwarsa (Testing) → regenerate `YT_REFRESH_TOKEN`.
- rclone/Drive musik gagal: cek base64 `GDRIVE_SA_JSON`, `GDRIVE_MUSIC_FOLDER_ID`, sharing folder musik ke SA.
- Pexels download gagal: `file_url` di pool perlu diperbarui.
- AI gagal/rate limit: cek key, model `:free`, atau fallback provider.
- Commit log gagal: cek Workflow permissions (Read and write).
- `quotaExceeded` (YouTube): cek kuota di Google Cloud Console.
