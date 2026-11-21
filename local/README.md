# Alur Lokal (terpisah dari GitHub)

Folder ini berisi **seluruh kebutuhan alur lokal** pembuatan video (VO + transkrip bertiming), terpisah dari pipeline/workflow GitHub (`.github/workflows/shorts.yml`, `scripts/plan.py`, `scripts/render.py`) yang **tidak diubah**.

Fokus awal: **Bahasa Inggris (EN)**, 1 video per eksekusi, self-contained di folder eksekusi.

## Struktur

- `template/` — template kanonik (skema + contoh #1). **Jangan diubah** kecuali memang ingin memperbarui template dasar.
- `execution/` — folder kerja **aktif** untuk 1 video. Awalnya identik dengan `template/`. **Script hanya membaca data dari sini**.
- `archive/` — riwayat eksekusi yang sudah dipakai (dipindahkan dari `execution/`, lalu `execution` di-reset dari `template/`).

## Cara kerja (ringkas)

1. **Siapkan data di `execution/`** (salin/ubah dari template):
   - `quote.json` — quote terpilih (id, author, lines, emphasis, bahasa).
   - `transcript.json` — naskah/segmen bertimestamp (detik) hasil final (VO + transkrip sudah jadi). **Sumber kebenaran timing/teks saat render.**
   - `vo/vo.mp3` — file voiceover.
   - `config.json` — pengaturan render/visual/audio dan **media** (seed keyword & hasil resolve).
   - `youtube.json` — metadata YouTube (judul, deskripsi, caption, hashtag/tag, privacy) untuk output & upload nanti.
   - `caption_styles.json` *(opsional, override lokal)* — jika ada, override sumber gaya bersama `config/caption_styles.json` (kanonik).
2. **(Opsional, boleh pakai AI/API)** `prepare` — menyiapkan/mengunduh media ke `execution/work/` berdasarkan seed di `config.json` (lihat "Media").
3. **(Opsional, boleh pakai AI)** `caption` - menentukan/mengisi **caption** lokal: **jika `youtube.json.caption` sudah disediakan (terisi), langsung dipakai (tidak diubah)**; jika kosong/belum disediakan (`caption` default template kosong), AI **selalu** membuat caption. Sistem memilih **1 gaya** dari metadata gaya caption bersama (`config/caption_styles.json`, atau override `caption_styles.json` di folder eksekusi bila ada): **acak** secara default, atau pakai preferensi eksplisit `caption_style`/`preferred_caption_style` di `youtube.json` jika cocok — AI menerima **hanya gaya terpilih itu** (bukan semua gaya). Hasil ditulis ke `youtube.json` (+ sinkron ke `out/` bila sudah ada). Bisa dijalankan sebelum atau sesudah render. *(Mulai dari caption dulu; deskripsi menyusul.)*
4. **Eksekusi render (deterministik, TANPA AI)** — saat kamu perintahkan **"eksekusi video lokal"**, jalankan render: script membaca seluruh kebutuhan dari `execution/` dan menghasilkan video di `execution/out/`.
5. **Arsipkan** — setelah selesai dipakai/dicoba, pindahkan `execution/` ke `archive/` dan reset `execution/` dari `template/` untuk video berikutnya.
6. **Upload YouTube** - dilakukan nanti (lokal), setelah beberapa percobaan berhasil. `execution/out/manifest.json`, `caption.txt`, dan `description.txt` disiapkan kompatibel.

> **Pemisahan lokal vs GitHub (sementara):** metadata gaya caption kini **bersama** di `config/caption_styles.json` (helper `scripts/caption_meta.py`), namun alur lokal memeriksa metadata lebih dulu — yang disediakan dipakai, yang kosong baru dibuat AI (mis. `caption`). Alur auto GitHub (`.github/workflows/shorts.yml`, `scripts/plan.py`, dsb.) **tetap terpisah dan perilakunya tidak diubah** pada perubahan ini; adopsi penuh metadata/caption AI ke alur GitHub adalah langkah lanjutan terpisah (perbedaan utama yang tersisa: pembuatan video).

## Perintah (jalankan dari root repo: `C:\Users\LENOVO\shorts-bot`)

```powershell
# 1) Siapkan/resolve media (seed keyword dulu; jika kurang & diizinkan, AI bantu keyword). Butuh PIXABAY_API_KEY & internet untuk Pixabay/Freetouse.
python scripts/local_workflow.py prepare

# 2) (opsional, AI) generate caption jika belum disediakan — baca gaya caption (config/caption_styles.json / override) + konteks, tulis ke youtube.json (dan out/ bila ada)
python scripts/local_workflow.py caption

# 3) EKSEKUSI VIDEO LOKAL (deterministik, tanpa AI) — baca semua data dari local/execution/
python scripts/local_workflow.py render

# 4) Arsipkan execution saat ini lalu reset execution dari template
python scripts/local_workflow.py archive

# (opsional) paksa reset execution dari template tanpa arsip (HATI-HATI: menimpa execution)
python scripts/local_workflow.py reset
```

Opsi berguna:
- `--dir local/execution` (default) ganti folder eksekusi.
- `--label nama` pada `archive` untuk label arsip.

## Skema file di `template/` / `execution/`

### `quote.json`
Data quote terpilih (self-contained). Dipakai untuk isi **quote card akhir** dan metadata.
- `id`, `author`, `language`
- `lines`: array string (baris kutipan)
- `emphasis`: array frasa yang di-emphasis pada quote card (dicocokkan sebagai substring dalam baris)
- `notes`: opsional

### `transcript.json` (inti, data-driven)
Sumber timing/teks narasi. Render membaca ini secara deterministik.
- `voiceover_file`: path file VO relatif ke folder eksekusi (contoh `vo/vo.mp3`).
- `text_fade_seconds`: durasi fade in/out default per segmen narasi (detik).
- `intro_backsound_seconds`: jeda intro (default `1.0`). **Detik 0 → intro hanya backsound** (tanpa teks/VO). `start/end` segmen dinyatakan **relatif terhadap VO** (mulai 0.0), dan render menggeser tampilan teks + audio VO sebesar intro sehingga **segmen teks pertama tampil mulai di detik `intro`** (mis. intro 1s → segmen 1 tampil di 1s).
- `segments`: array segmen narasi berurutan, tiap segmen:
  - `start`, `end`: detik relatif VO (float).
  - `video_keyword`: *(opsional)* pengendali background segmen ini (bagian visual **spesifik**, diprioritaskan).
    - **Terisi (bukan keep)** → `prepare` memakai **AI untuk menerjemahkan/menafsirkan** frasa tersebut menjadi keyword visual stok **Bahasa Inggris** (prioritas utama, label `video_keyword-ai`; fallback ke teks asli jika AI tidak tersedia). Bisa ditulis bebas (ID/EN/deskriptif).
    - **kosong** → `prepare` (per-segment) resolve otomatis: (2) keyword turunan dari `emphasis` segmen → EN, lalu (3) AI menafsirkan transkrip segmen → EN.
    - **`"keep"`** (alias `"continue"`/`"same"`/`"hold"`) → **tidak ganti video**; lanjutkan klip segmen sebelumnya (tanpa cut di segmen ini). Segmen pertama selalu mulai klip; segmen terakhir selalu lanjut.
  - `lines`: array **baris layar**. Tiap baris adalah array **parts**: `[{"text":"...","emphasis":true|false}, ...]` (mendukung emphasis/tebal-miring dalam 1 baris).
  - `author`: string (mis. `"- seneca -"`) atau `null` (ditampilkan di bawah blok segmen itu).
- `card`: quote card akhir (isi diambil dari `quote.json` bila `use_quote=true`):
  - `enabled`, `use_quote`, `start_offset_after_vo`, `fade_in`, `hold`, `fade_out`, `tail`.

Total durasi ≈ `intro_backsound_seconds` + durasi VO + `start_offset_after_vo` + `fade_in` + `hold` + `fade_out` + `tail` (mengikuti VO sebagai acuan). Overlay teks narasi mengikuti `start/end` yang digeser `+intro`.

### `config.json`
Pengaturan render & media.
- `render`: `ffmpeg`/`ffprobe` (null = auto-detect PATH / lokasi umum Windows), ukuran/fps/crf/preset/bitrate.
- `visual`: `slowdown`, `xfade_duration`, `background_count`, grading/gelap (`brightness`, `saturation`, `contrast`, `darken`).
- `audio`: `narration_music_volume`, `card_music_volume` (musik naik saat card), `music_fade_out`.
- `media.backgrounds`: `source` (pixabay), `mode`:
  - `per_segment` *(disarankan)*: **1 klip per segmen teks**, selaras timing. Butuh `transcript.json`. Titik ganti klip = awal segmen (setelah intro), **kecuali** segmen `video_keyword: "keep"` (alias `continue`/`same`/`hold`) yang melanjutkan klip sebelumnya. Segmen pertama selalu mulai klip; segmen terakhir selalu lanjut → `prepare` me-resolve **1 klip per titik ganti** ke `work/seg_bg_*.mp4` (≤ `N-1` untuk `N` segmen).
    - Prioritas keyword per klip (Pixabay, **bahasa Inggris**): **(1)** `video_keyword` segmen (spesifik, diutamakan) → AI terjemahkan/cari keyword EN → **(2)** dari `emphasis` segmen → EN → **(3)** AI tafsir transkrip segmen → EN. Fallback: `seed_keywords` (hanya jika tidak ada kandidat). Segmen `"keep"` tidak me-resolve klip baru.
  - `legacy`: `background_count` klip global dibagi merata (seed `seed_keywords` + opsional AI keyword fallback), disimpan `work/bg_*.mp4`.
  - `seed_keywords`: fallback/global, `allow_ai_keywords_fallback`: izinkan bantuan AI untuk turunan/tafsir keyword, `resolved_files`: path relatif ke eksekusi (dipakai `render`; jika jumlah kurang, dipakai berulang).
- `media.music`: `source` (freetouse), `seed_query`, `resolved_file`, metadata (title/artist/url/license_note). Musik via seed (non-LLM pada desain saat ini).
- `paths`: `voiceover`, `work_dir`, `out_dir`.

**Pemisahan prepare vs render:** `prepare` boleh pakai AI/API & internet untuk me-resolve/mengunduh media/keyword ke `work/` dan memperbarui `resolved_*`. `render` **tanpa AI**, hanya memakai file/data yang sudah ada di folder eksekusi (deterministik). `caption` memakai AI hanya bila `youtube.json.caption` kosong.

### Gaya caption (`config/caption_styles.json`)
Sumber kanonik bersama: **`config/caption_styles.json`** (dibaca via `scripts/caption_meta.py`). Folder eksekusi dapat memiliki `caption_styles.json` sebagai **override lokal** opsional; jika tidak ada, dipakai sumber bersama.
- `notes`: panduan umum (kejelasan kata awal, nada selaras VO, dll.).
- `styles[]`: tiap gaya berisi `id`, `group`/`group_label`, `name`, `intent`, `guidance`, `examples[]`.
- Saat caption di-generate (AI, hanya jika `youtube.json.caption` kosong): sistem memilih **1 gaya** (acak, atau `caption_style`/`preferred_caption_style` di `youtube.json` jika cocok) dan mengirim **hanya gaya terpilih** ke AI. Hasil AI dapat mencatat `caption_source`, `caption_style_id`, `caption_style_name`, `caption_reason`.

### `youtube.json`
Metadata YouTube (disiapkan sekarang, upload nanti). `render` menyalinnya ke `out/manifest.json` (kompatibel publisher: `title`, `description`, `hashtags`, `privacy`), `out/caption.txt`, dan `out/description.txt`.
- `title`, `description`, `caption`, `hashtags`/`tags`, `privacy` (`private`/`public`/`unlisted`), `categoryId`, `defaultLanguage`, `defaultAudioLanguage`, `madeForKids`.
- **Lokal:** jika `caption` sudah diisi → dipakai apa adanya. Jika kosong → `python scripts/local_workflow.py caption` mengisinya via AI (berdasarkan **1 gaya terpilih** dari `config/caption_styles.json` / override lokal + konteks quote/transkrip; acak atau `caption_style`/`preferred_caption_style` jika cocok). `render` tetap deterministik (tidak memanggil AI).

### Folder `vo/`, `work/`, `out/`
- `vo/` — file VO (contoh `vo.mp3`).
- `work/` — media kerja/hasil unduh (background, musik). `render` membaca dari sini sesuai `resolved_*`.
- `out/` - hasil: `final.mp4`, `manifest.json`, `caption.txt`, `description.txt`, `render_info.json` (+ intermediate render disimpan di subfolder tmp saat proses).

## Contoh & status eksekusi
- `template/` adalah template kanonik (skema + contoh #1 Seneca, termasuk mekanisme per-segmen/intro) sebagai acuan format. Gaya caption kanonik bersama ada di `config/caption_styles.json` (bukan salinan per-folder).
- `execution/` saat ini disiapkan untuk **quote 150 (ID, Anonim — narasi reflektif "Kamu tidak tertinggal…")**: `quote.json`/`transcript.json` (15 segmen, `intro_backsound_seconds` 1s, emphasis ditentukan, `video_keyword` kosong semua; tersedia nilai `"keep"`/`"continue"` untuk lanjutkan klip tanpa ganti), `config.json` (`media.backgrounds.mode=per_segment`), `youtube.json` (caption kosong), musik resolved contoh. **Belum siap render** sampai file VO (`vo/vo.mp3`) dimasukkan, timing `start/end` disesuaikan ke durasi VO nyata, dan background per-segmen di-resolve (`prepare`). Output render sebelumnya (jika ada) mungkin masih tersisa di `out/`.

> Catatan: `render` deterministik dan tidak memanggil AI. `prepare` dapat memakai AI/API untuk me-resolve media/keyword per-segmen (EN). `caption` (lokal) memakai AI hanya untuk mengisi caption bila belum disediakan (jika sudah diisi, dipakai apa adanya). Alur auto GitHub tetap terpisah/tidak diubah. Upload ke YouTube/channel berbeda (akun sama) dilakukan belakangan dengan kredensial/target channel yang benar.
