# Rencana Refactoring Bertahap — `shorts-bot`

Dokumen ini menyusun rencana **refactoring bertahap** (perbaikan struktur internal **tanpa mengubah perilaku/hasil** yang terlihat) untuk:
1. **Efisiensi & maintainability**: kode lebih mudah dipahami, diuji, dan dioptimalkan.
2. **Kesiapan multi-platform**: memudahkan penambahan distribusi/upload ke media sosial lain (mis. **TikTok, Meta/Instagram-Facebook, X**) di samping YouTube & arsip Drive yang sudah ada.

> Status: **Fase 0–4 selesai** (terimplementasi & terverifikasi). Fase 5 (opsional/lanjutan) belum dijalankan. Setiap fase dijalankan bertahap dan diverifikasi.

## Prinsip & guardrails (berlaku di semua fase)
- **Paritas perilaku:** output fungsional tetap sama (alur `plan.py` → `render.py`, isi `render_plan.json`/`out/final.mp4`/`out/caption.txt`/`out/manifest.json`, format log/metadata `used_quotes.jsonl`, `used_videos.jsonl`, `used_music.jsonl`, `pixabay_cache.json`, serta alur arsip/upload YouTube yang ada) kecuali dinyatakan eksplisit.
- **Bertahap & kecil:** satu fase/PR-logis dalam satu waktu, mudah di-review dan di-rollback.
- **Terverifikasi:** setiap fase ditutup dengan verifikasi (`python -m py_compile` pada modul terkait + uji end-to-end `plan.py` → `render.py`; uji publish/arsip bila fase menyentuhnya, atau verifikasi struktur/dry-run yang setara bila kredensial tidak tersedia).
- **Media tetap ephemeral:** file media (`work/`, `out/`, `render_plan.json`) tidak di-commit; metadata/log tetap di-commit sesuai kebijakan saat ini.
- **Rahasia aman:** tidak mengubah/mengekspos secrets; penambahan platform memakai secrets/env terpisah.
- **Tanpa perubahan fitur terselubung:** refactoring bukan penambahan platform baru; integrasi platform baru dilakukan terpisah setelah fondasinya siap.

## Peta kondisi saat ini (ringkas)
- **Orkestrasi/konten:** `scripts/plan.py` (besar, multi-tanggung-jawab) menangani config/env, mode quote `list/famous/custom`, AI, pemilihan latar/musik, normalisasi, pembuatan rencana/deskripsi, dan penulisan log/metadata.
- **Sumber media:** `scripts/pixabay.py` (Pixabay + keyword AI + filter + cache) dan `scripts/freetouse.py` (Freetouse, filter non-premium/calm-motivasi/durasi) — logika domain bercampur dengan `SystemExit`/CLI; ada pola utilitas serupa (fetch/download/seed).
- **AI:** `scripts/ai.py` (adapter provider, parsing JSON toleran, retry/fallback).
- **Render:** `scripts/render.py` menghasilkan `out/final.mp4`, `out/caption.txt`, `out/manifest.json` dari `render_plan.json` (kontrak artefak sudah ada, belum diformalkan).
- **Distribusi:** `scripts/archive_drive.py` (arsip ke Drive via OAuth user, `gauth.py`), `scripts/publish.py` (upload YouTube resumable, mapping metadata YouTube hardcoded). Workflow CI memanggil langkah tetap: plan → render → arsip Drive → upload YouTube → commit log/metadata.
- **Dokumentasi:** `README.md`, `docs/RUNNING_LOCAL.md` sudah mengikuti alur API saat ini.

---

## Fase 0 — Baseline & penjagaan perilaku
**Tujuan:** menetapkan acuan perilaku saat ini agar refactoring berikutnya bisa diverifikasi (tidak mengubah hasil).

- **Kondisi/prasyarat:**
  - Dilakukan **sebelum** perubahan struktur kode apa pun.
  - Akses untuk menjalankan uji lokal (Python, ffmpeg/ffprobe, `PIXABAY_API_KEY`, internet; AI opsional/fallback) tersedia, atau disepakati metode verifikasi alternatif.
- **Usulan yang dilakukan:**
  - Dokumentasikan (di catatan PR/issue atau bagian kerja) perilaku & artefak acuan: struktur kunci `render_plan.json`, `out/manifest.json`, `out/caption.txt`, skema/field log `used_*.jsonl` & `pixabay_cache.json`, serta langkah CI relevan.
  - Tetapkan **checklist verifikasi** standar per fase: `py_compile`, e2e `plan.py` → `render.py`, inspeksi diff struktur output/metadata (bukan byte-identik media, karena unduhan acak/API), dan cek tidak ada file media ter-stage.
  - (Opsional, bila membantu) simpan contoh manifest/plan ter-redaksi sebagai referensi struktur (tanpa data sensitif).
  - Identifikasi bagian berisiko (parsing AI, pemilihan acak ber-seed, format deskripsi/log) agar diuji eksplisit.
- **Keluaran:** baseline & checklist verifikasi yang disepakati.
- **Verifikasi:** checklist dapat dijalankan dan merepresentasikan perilaku saat ini.
- **Risiko/catatan:** output media non-deterministik lintas run (sumber API/acak) — verifikasi fokus pada struktur, field wajib, dan keberhasilan alur.

**Status:** ✅ selesai (baseline tercatat).

**Baseline teramati (2026-11-19, repo saat ini):**
- `python -m py_compile` lulus untuk semua script di `scripts/` (`ai.py`, `archive_drive.py`, `encode_sa.py`, `freetouse.py`, `gauth.py`, `get_refresh_token.py`, `pexels.py`, `pixabay.py`, `plan.py`, `publish.py`, `render.py`).
- **`render_plan.json`** (kontrak plan→render): memuat key inti/metadata & render params antara lain `date, theme, mode, source, id, language, quote, author, duration, lines, quote_line_segments, author_display, author_is_dash, title, caption, hashtags, description, privacy, background, background_meta, music, music_meta` + parameter tipografi/layout/visual/audio (`quote_font_size`, `author_font_size`, `line_spacing`, `max_text_width`, `fade_in_*`, `line_gap`, `band_*`, `overlay_opacity`, `full_overlay_opacity`, `band_feather`, `brightness`, `saturation`, `music_volume`, `dash_*`, warna).
- **`out/manifest.json`**: `file, duration, width, height, size_bytes, theme, mode, quote, author, language, lines, title, caption, hashtags, description, privacy, background_meta, render`. **`out/caption.txt`**: isi deskripsi/atribusi siap tempel.
- **Log/metadata (skema teramati pada entri terbaru):**
  - `data/used_quotes.jsonl`: `ts, date, mode, source, id, language, quote, author, lines, title, background, music`.
  - `data/used_videos.jsonl`: `ts, date, run_seed, quote_id, quote, duration_target, background`.
  - `data/used_music.jsonl`: `ts, date, run_seed, quote_id, duration_target, music`.
  - `data/pixabay_cache.json`: cache keberhasilan latar (dipakai sebagai fallback).
- **Checklist verifikasi per fase:** (1) `python -m py_compile` modul terdampak, (2) e2e `scripts/plan.py` → `scripts/render.py` sukses (dengan env/ffmpeg/internet yang sesuai), (3) struktur/field wajib artefak & log tetap setara baseline (nilai/ID media boleh berbeda), (4) tidak ada `work/`, `out/`, `render_plan.json` atau media ter-stage/ter-commit. Area sensitif: parsing AI & fallback, pemilihan acak ber-seed, format deskripsi/atribusi, skema log.

## Fase 1 — Rapikan orkestrasi, konfigurasi, & logging (fondasi)
**Tujuan:** membuat alur konten lebih modular dan mudah diubah tanpa mengubah hasil.

- **Kondisi/prasyarat:**
  - Fase 0 (baseline/checklist) tersedia.
  - Tidak ada kebutuhan mengubah perilaku/format output pada fase ini.
- **Usulan yang dilakukan:**
  - Pecah tanggung jawab `scripts/plan.py` menjadi unit yang jelas (fungsi/modul), mis. pemuatan config/env/path, resolusi quote per mode (`list`/`famous`/`custom` + normalisasi), perakitan rencana & deskripsi/atribusi, dan penulisan log — dengan `plan.py` sebagai orkestrator tipis.
  - Sentralisasi pembacaan defaults/path (`quotes/used/cache/used_videos/used_music`) dan utilitas bersama kecil (mis. load `.env`, helper JSON/JSONL) untuk mengurangi duplikasi/magic string.
  - Satukan penulisan metadata run: helper yang menyusun & menulis `used_quotes.jsonl`, `used_videos.jsonl`, `used_music.jsonl` secara konsisten dari konteks run (ts/date/seed/quote/bg/music) **dengan field/format tetap sama**.
  - Rapikan penamaan & struktur kode (tanpa ubah logika), tambahkan docstring seperlunya pada titik batas.
- **Keluaran:** struktur kode lebih terpisah; perilaku & artefak setara baseline.
- **Verifikasi:** `py_compile` + e2e `plan.py` → `render.py`; bandingkan struktur/field `render_plan.json`, `manifest.json`, `caption.txt`, dan entri log terhadap baseline.
- **Risiko/catatan:** regresi halus pada normalisasi/format deskripsi — mitigasi dengan verifikasi struktur & kasus representatif (list/famous fallback/custom).

**Status:** ✅ selesai.
- Implementasi: `scripts/common.py`, `scripts/runlog.py`, refactor `scripts/plan.py` (orkestrasi + helper terpisah, logging terpusat) dengan paritas perilaku/skema. Terverifikasi `py_compile` + e2e `plan.py` → `render.py` dan pemeriksaan struktur/log.

## Fase 2 — Modularisasi sumber media & utilitas bersama (siap efisiensi)
**Tujuan:** merapikan integrasi Pixabay/Freetouse/AI dan utilitas bersama agar mudah dioptimalkan (retry, timeout, caching, strategi seleksi) tanpa mengubah hasil.

- **Kondisi/prasyarat:**
  - Fase 1 stabil & terverifikasi.
  - Perilaku pemilihan media saat ini diterima sebagai acuan.
- **Usulan yang dilakukan:**
  - Ekstrak utilitas bersama untuk pola berulang: fetch JSON HTTP, unduh file, pemilihan acak deterministik berbasis seed, dan helper cache (baca/tulis, dedupe/cap) — gunakan di `pixabay.py`/`freetouse.py` (dan tempat lain bila relevan) dengan hasil setara.
  - Pisahkan logika domain dari kontrol CLI: modul sumber media melempar exception bermakna (mis. kegagalan fetch/tidak ada kandidat) dan entrypoint/orkestrator memutuskan fallback/exit & pesan **dengan perilaku pengguna tetap sama** (termasuk fallback cache Pixabay & fallback musik lokal).
  - Rapikan struktur `ai.py`/pemanggilan AI bila ada duplikasi jelas (tanpa ubah kontrak prompt-output yang sudah bekerja) dan pastikan penanganan error/fallback tetap konsisten.
  - Sentralisasi konstanta/parameter yang saat ini tersebar (timeout, batas kandidat, ambang durasi, daftar query/mood, limit cache) ke lokasi yang jelas (config/konstanta bernama) dengan nilai default sama.
- **Keluaran:** modul media/utilitas lebih bersih & dapat diuji; jalur siap untuk efisiensi di fase lanjutan.
- **Verifikasi:** `py_compile` + e2e; cek pemilihan/fallback masih berfungsi (termasuk skenario cache/fallback yang dapat disimulasikan) dan metadata/log setara.
- **Risiko/catatan:** perubahan pada seed/urutan acak dapat mengubah pilihan meski “valid” — pertahankan mekanisme seed/seleksi agar ekuivalen.

**Status:** ✅ selesai.
- Implementasi: `scripts/media_utils.py`, refactor `scripts/pixabay.py` & `scripts/freetouse.py` (utilitas bersama, exception domain + boundary/exit/pesan & fallback setara, konstanta dipertahankan). `scripts/ai.py` tidak diubah (tanpa duplikasi jelas yang aman). Terverifikasi `py_compile` + e2e `plan.py` → `render.py` dan pemeriksaan struktur/log.

## Fase 3 — Kontrak konten kanonik & abstraksi publish (paritas YouTube/arsip)
**Tujuan:** memformalkan artefak konten dan memisahkan publikasi agar **menambah platform baru tidak menyentuh render/inti konten**, sambil menjaga YouTube & arsip Drive tetap bekerja sama.

- **Kondisi/prasyarat:**
  - Fase 1–2 stabil (struktur siap dipisah).
  - Disepakati bahwa YouTube + arsip Drive adalah perilaku acuan yang harus dipertahankan.
- **Usulan yang dilakukan:**
  - Definisikan **konten kanonik/kontrak artefak** berbasis keluaran render saat ini (mis. representasi `Content/Manifest`: video, title, caption, description, hashtags, privacy, quote/author, metadata latar/musik/atribusi) agar menjadi sumber kebenaran tunggal bagi distribusi.
  - Refactor `scripts/publish.py` menjadi lapisan terstruktur: **formatter metadata YouTube** (batas/title/description/tags/privacy/category seperti sekarang) + **publisher YouTube** (upload resumable) di balik antarmuka umum (mis. `Publisher.publish(...)`), dengan dispatcher yang saat ini menargetkan YouTube saja.
  - Rapikan pemisahan auth: `gauth.py`/kredensial Google digunakan secara eksplisit untuk target Google (YouTube/Drive) agar penambahan auth platform lain tidak bercampur.
  - Pertahankan `scripts/archive_drive.py` sebagai target distribusi/arsip terpisah; (opsional) selaraskan ke pola target yang sama bila tanpa ubah perilaku.
  - Sesuaikan orkestrasi (script pemanggil dan/atau langkah workflow) agar membaca target aktif (default: arsip Drive + YouTube) **dengan urutan & hasil setara**.
- **Keluaran:** jalur publish terabstraksi, YouTube/Drive paritas; siap ditambah target.
- **Verifikasi:** `py_compile` + e2e render; verifikasi alur publish/arsip menghasilkan perilaku setara (uji nyata bila kredensial tersedia, atau verifikasi pemetaan metadata/request & dry-run yang aman bila tidak).
- **Risiko/catatan:** area sensitif kredensial/API — lakukan perubahan kecil, uji terbatas, dan sediakan jalur fallback/kompatibilitas pemanggilan lama bila perlu.

**Status:** ✅ selesai.
- Implementasi: `scripts/content.py` (kontrak/konten kanonik dari `out/manifest.json` + video), `scripts/publish_youtube.py` (formatter metadata YouTube + upload resumable, pemetaan identik), `scripts/publish.py` sebagai dispatcher target publish (default `youtube`, paritas perilaku/output YouTube). `scripts/archive_drive.py` & `scripts/gauth.py` dipertahankan untuk target Google/arsip. Workflow publish diberi env opsional dengan default kompatibel.
- Verifikasi: `py_compile` modul publish/konten; formatter YouTube diverifikasi identik terhadap logika/manifest saat ini (pemetaan `snippet/status` & batas). Alur CI default tetap: arsip Drive → publish YouTube. Upload nyata tidak diuji ulang di lokal (butuh kredensial/sisi YouTube), kontrak pemetaan dipertahankan.

## Fase 4 — Multi-target & penyiapan platform baru (TikTok, Meta, X)
**Tujuan:** memungkinkan render sekali lalu distribusi ke beberapa platform melalui formatter/publisher per platform.

- **Kondisi/prasyarat:**
  - Fase 3 stabil (antarmuka publisher & konten kanonik tersedia, paritas YouTube terjaga).
  - **Kebutuhan produk & akses tersedia per platform:** akun/developer app, izin/API access, kredensial/secrets, dan keputusan kebijakan konten/privasi yang sesuai (TikTok/Meta/X memiliki syarat & approval berbeda).
  - Batasan platform diketahui (panjang caption/teks, dukungan title/tag/hashtag, format media, mode privasi).
- **Usulan yang dilakukan:**
  - Tambahkan **formatter metadata per platform** dari konten kanonik (YouTube tetap, plus TikTok/Meta/X) sesuai batas & konvensi masing-masing (tanpa mengubah formatter YouTube).
  - Implementasikan **publisher per platform** bertahap (dapat dimulai sebagai stub/dry-run terbatas bila API/akses belum siap, lalu diaktifkan saat kredensial siap): mis. TikTok, Meta (IG/Facebook), X — masing-masing menangani auth, upload media, dan pembuatan post/publish sesuai API.
  - Tambahkan konfigurasi target (mis. `PUBLISH_TARGETS`/toggle per platform) dan pemetaan secrets/env per platform; orkestrator mem-publish ke target aktif dan melaporkan hasil per target (gagal satu target tidak harus merusak artefak render; kebijakan lanjut/gagal-parsial ditetapkan eksplisit).
  - Perbarui workflow CI & dokumentasi (README/RUNNING_LOCAL) untuk secrets/opsi multi-platform.
- **Keluaran:** kerangka multi-platform siap pakai/diaktifkan per platform seiring ketersediaan akses.
- **Verifikasi:** uji per platform secara terisolasi (sandbox/akun uji bila ada), verifikasi formatter (batas/pemetaan field), dan regresi YouTube/Drive.
- **Risiko/catatan:** ketergantungan pada approval & perubahan API pihak ketiga; rilis bertahap per platform disarankan.

**Status:** ✅ selesai (kerangka/scaffolding; publish nyata per platform bertahap).
- Implementasi: `scripts/publish_platforms.py` (formatter metadata per platform TikTok/Meta/X dari konten kanonik + publisher stub/dry-run), dispatcher `scripts/publish.py` mendukung `PUBLISH_TARGETS` (default `youtube`), `PUBLISH_DRY_RUN`, `PUBLISH_FAIL_FAST` (default 1, gagal cepat; bisa 0 untuk lanjut parsial) dengan ringkasan per target. Formatter YouTube tidak diubah.
- Batas/kebijakan: TikTok/Meta/X memerlukan akun/app, izin/API, kredensial & implementasi API nyata; saat ini target non-YouTube mendukung verifikasi formatter via dry-run dan memberi error jelas bila kredensial/implementasi nyata belum siap (tidak publish palsu). Workflow & dokumentasi diperbarui dengan opsi/secrets terpisah.
- Verifikasi: `py_compile` modul terkait; regresi jalur default YouTube dipertahankan (formatter paritas). Uji publish nyata platform baru menunggu akses/kredensial & implementasi API masing-masing.

## Fase 5 (opsional/lanjutan) — Efisiensi lanjutan & hardening
**Tujuan:** optimasi dan keandalan setelah struktur stabil.

- **Kondisi/prasyarat:** Fase 1–3 (dan bagian Fase 4 yang relevan) stabil, ada metrik/kebutuhan efisiensi yang jelas.
- **Usulan yang dilakukan (contoh, dipilih sesuai kebutuhan):** caching/reuse unduhan yang aman, strategi retry/backoff & timeout terpadu, paralelisasi aman pada langkah independen, pengurangan kerja render berulang, observability/log ringkas per langkah, dan hardening error-handling.
- **Keluaran & verifikasi:** perbaikan terukur (waktu/keandalan/biaya) dengan paritas perilaku & uji regresi.

**Status:** ✅ selesai (hardening & efisiensi terbatas, perilaku/kontrak dipertahankan).
- **Implementasi:**
  - `scripts/media_utils.py`: retry/backoff terbatas & terpadu untuk fetch/download HTTP (urllib/requests) pada kegagalan transient (timeout/koneksi, 429/5xx) — meningkatkan keandalan tanpa mengubah hasil sukses.
  - `scripts/pixabay.py`: pemilihan akhir kandidat (dari top hasil terfilter) dibuat deterministik berbasis seed/RNG terisolasi (perbaikan konsistensi seed) sehingga aman untuk eksekusi paralel.
  - `scripts/plan.py`: pengambilan latar (Pixabay) dan musik (Freetouse) dijalankan **paralel** setelah quote/durasi diketahui (langkah independen, I/O-bound) untuk efisiensi waktu; ditambah observability waktu langkah/total. Kontrak rencana, format log/metadata, dan mekanisme fallback/seleksi tetap setara.
  - `scripts/render.py`: hardening cek ketersediaan `ffmpeg`/`ffprobe` dengan pesan jelas, serta observability waktu render/total. Pipeline/filter/artefak output tidak diubah.
- **Verifikasi:** `python -m py_compile` pada modul terdampak lulus; e2e `plan.py` → `render.py` lulus (artefak `render_plan.json`, `out/final.mp4`, `out/caption.txt`, `out/manifest.json` valid & struktur setara). Karena pemilihan media bergantung seed/API/jaringan, verifikasi difokuskan pada keberhasilan alur, struktur/field wajib, dan paritas perilaku (bukan identitas media byte-per-byte).

---

## Definisi selesai per fase (ringkas)
- Kode lulus `py_compile` (modul terdampak) dan verifikasi e2e sesuai checklist fase.
- Tidak ada regresi perilaku/format output yang disyaratkan; media tidak ter-commit; dokumentasi diperbarui bila antarmuka/konfigurasi berubah.
- Perubahan direview dan disepakati sebelum lanjut ke fase berikutnya.
