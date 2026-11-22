# PROJECT CONTEXT — `shorts-bot`

> **Tujuan dokumen:** konteks utuh yang bisa dipanggil di sesi AI lain agar agent cepat memahami peta proyek, batas sistem, alur kerja, status saat ini, dan celah terbuka.  
> **Tanggal snapshot:** 2026-11-22  
> **Sumber kebenaran utama:** kode dan file di repo ini. Jika dokumen ini konflik dengan kode, ikuti kode lalu perbarui dokumen.

---

## 1) Ringkasan Proyek

`shorts-bot` adalah repo automasi pembuatan YouTube Shorts bertema quotes/motivasi/refleksi. Repo ini memiliki **dua mode operasional yang berbeda**:

1. **Workflow GitHub (cloud/CI, otomatis)** — berjalan lewat GitHub Actions untuk produksi/publikasi terjadwal atau manual dispatch.
2. **Workflow Lokal (local/standalone, manual/agent-assisted)** — berjalan di mesin lokal untuk persiapan, eksperimen, debug, render terkontrol, dan iterasi tanpa auto-publish/auto-commit.

Keduanya berbagi tujuan akhir (video Shorts siap publikasi), tetapi **berbeda konteks eksekusi, sumber data, kontrol status, keamanan kredensial, dan efek samping**.

## 2) Snapshot Repo Saat Ini

- **Repo:** `C:\Users\LENOVO\shorts-bot`
- **Remote:** `origin git@github.com-dailyboost:dailyboostwithwicaksono-rgb/shorts-bot.git`
- **Branch:** `main`
- **Commit terbaru saat snapshot:**
  - `03c548e fix: improve GitHub workflow caption and description generation`
  - `427e9f0 chore: update logs/metadata (run 21)`
- **Status kerja:** repo bisa dirty/uncommitted; banyak file lokal/work-in-progress dapat ada. Jangan commit secret atau file tak terkait.
- **Catatan penyesuaian CI (2026-11-22):** alur GitHub sedang diselaraskan ke terminologi `title` kanonik (`caption` jadi alias legacy). Perubahan ini belum tentu sudah di-commit; cek `git status` sebelum mengira CI sudah memakainya.

## 3) Perbedaan Utama: GitHub Workflow vs Lokal

| Aspek | GitHub Workflow (CI/Cloud) | Lokal (`local/`) |
|---|---|---|
| **Lokasi utama** | `.github/workflows/shorts.yml`, `scripts/`, `config/`, `assets/`, `data/`, `work/`, `out/` | `local/scripts/`, `local/config/`, `local/assets/`, `local/templates/`, `local/execution/`, `local/archive/` |
| **Trigger** | `schedule` cron (UTC) + `workflow_dispatch` | CLI manual: `python local/scripts/local_workflow.py ...` |
| **Lingkungan** | `ubuntu-latest`, ffmpeg dipasang di job, dependency via `requirements.txt` | Mesin lokal Windows/user, ffmpeg lokal, env opt-in lokal |
| **Tujuan** | Produksi otomatis end-to-end sampai publish/distribusi | Produksi terkontrol, debug, iterasi, verifikasi sebelum publish |
| **Input konten** | `scripts/plan.py` memilih/generate quote (list/famous/custom) + metadata + media plan | Operator/AI menyiapkan `quote.json`, `transcript.json`/TXT, `vo.mp3`, `youtube.json`, `config.json` di `local/execution` |
| **Status metadata** | Tidak memakai state machine `kosong/draft/valid/publish` lokal yang sama | Status-aware: `kosong/draft/valid/publish` untuk quote/transcript/youtube/config |
| **AI usage** | Dipakai saat plan/generate metadata sesuai mode; render ffmpeg deterministik | Pre-prepare/title/prepare dapat pakai AI/API; **render deterministik tanpa AI** |
| **Media** | Pixabay/Freetouse/API sesuai plan; cache/log di `data/` | Prepare resolve ke `local/execution/work/`; provider seam B3 (`adapters/media_provider.py`) |
| **Output** | `render_plan.json`, `out/final.mp4`/manifest/description; `out/caption.txt` = title (nama legacy), artifact, archive drive, publish | `local/execution/out/final.mp4`, `manifest.json`, `caption.txt`, `description.txt`, `render_info.json` |
| **Publish** | `scripts/publish.py` (default YouTube), kredensial dari GitHub Secrets/Vars | Tidak auto-upload. `publish` status saat ini bookkeeping/manual; upload nyata belum otomatis |
| **Efek samping repo** | Job commit log/metadata `data/*.jsonl` cache kembali ke branch | Tidak auto-commit. Archive/reset hanya memindahkan folder lokal |
| **Kredensial** | GitHub Secrets/Vars | `local/.env` (gitignored) -> root `.env` -> OS env |
| **Safety boundary** | Concurrency workflow, timeout, secrets GitHub | `LifecycleService` menolak operasi di luar `local_root`; jangan tulis secret ke git |
| **Cocok untuk** | Operasional rutin/terjadwal | Eksperimen, perbaikan pipeline lokal, review manusia, QA artefak |

## 4) Workflow GitHub (Cloud/CI)

### 4.1 File/Komponen Kunci

- `.github/workflows/shorts.yml` — definisi workflow.
- `scripts/plan.py` — membuat rencana konten: pilih quote (list/famous/custom), metadata, background/music, tulis `render_plan.json`.
- `scripts/render.py` — render video deterministik dari plan.
- `scripts/archive_drive.py` — arsip output ke Google Drive (OAuth user).
- `scripts/publish.py` / `scripts/publish_youtube.py` / `scripts/publish_platforms.py` — distribusi/upload (default target YouTube).
- `scripts/ai.py`, `scripts/pixabay.py`, `scripts/freetouse.py`, `scripts/title_meta.py`, `scripts/caption_meta.py` (shim legacy), dll. — helper AI/media/metadata.
- `config/title_styles.json` — sumber gaya judul CI (legacy: `config/caption_styles.json`).
- `data/` — cache/log: `used_quotes.jsonl`, `pixabay_cache.json`, `used_videos.jsonl`, `used_music.jsonl`, dll.
- `config/` dan `assets/` root — konfigurasi/tema/font bersama.

### 4.2 Trigger & Konfigurasi

Dari `shorts.yml`:
- **Schedule (UTC):** `0 20 * * *` (03:00 WIB) dan `0 11 * * *` (18:00 WIB).
- **Manual dispatch:** input `mode` (`list|famous|custom`), `quote_text`, `quote_author`, `quote_language`.
- **Concurrency:** group `shorts-bot`, `cancel-in-progress: false`.
- **Permissions:** `contents: write` (untuk commit metadata/log).

### 4.3 Urutan Job

1. Checkout repo.
2. Setup Python 3.12.
3. Install ffmpeg + cek font/assets.
4. `pip install -r requirements.txt`.
5. `python scripts/plan.py` dengan env AI/media/privacy/mode.
6. `python scripts/render.py`.
7. `python scripts/archive_drive.py` (Drive OAuth).
8. `python scripts/publish.py` (default `PUBLISH_TARGETS=youtube`, bisa dry-run/fail-fast).
9. Commit `data/used_*.jsonl`/cache jika berubah.
10. Upload artifact kecil (`render_plan.json`, `out/manifest.json`, `out/caption.txt` = title legacy, `out/description.txt`).

### 4.4 Efek Samping GitHub Workflow

- **Menulis/merubah**: `render_plan.json`, `out/*`, `work/*`, `data/*` cache/log.
- **Commit ke repo**: ya, untuk log/metadata cache (langkah commit).
- **Upload eksternal**: Drive archive dan publish target (YouTube default) bila kredensial aktif.
- **Rahasia**: GitHub Secrets/Vars; jangan bocor ke log.

### 4.5 Batasan/Aturan GitHub Workflow

- Jangan ubah perilaku workflow GitHub saat refactor lokal kecuali diminta eksplisit.
- Perubahan pada `scripts/plan.py`, `scripts/render.py`, `scripts/publish*.py`, `.github/workflows/shorts.yml` berdampak ke produksi CI.
- Default publish target harus tetap aman/kompatibel; dry-run tersedia via vars.

### 4.6 Title vs Caption di GitHub Workflow

- **Kanonik:** `title` (maks 100 karakter). Dihasilkan `scripts/plan.py` → `generate_styled_title()` → `scripts/title_meta.py` → `config/title_styles.json` → prompt `build_title_prompt()`, dengan fallback `title or caption` saat AI gagal.
- **Alias legacy:** `caption` selalu di-mirror dari title di `render_plan.json` dan `out/manifest.json`. Prompt AI lama yang membalas `caption` masih diterima oleh `generate_styled_title()`.
- **Artefak:** `out/caption.txt` berisi **title** (nama file dipertahankan untuk kompatibilitas `content.py`/publish/archive); `out/description.txt` dan `manifest.description` berisi deskripsi lengkap.
- **Kompatibilitas yang tidak boleh dihapus:** `scripts/caption_meta.py` (shim), `generate_styled_caption()` (alias), kunci `caption_style`/`preferred_caption_style`, dan field `caption*`.
- **Prasyarat CI:** `scripts/title_meta.py` dan `config/title_styles.json` harus ikut ter-commit. Jika tidak, `load_title_styles()` fallback ke `config/caption_styles.json` dan CI masih berperilaku/berlabel "caption".

## 5) Workflow Lokal (`local/`)

### 5.1 Tujuan Lokal

- Menjalankan pembuatan video secara **self-contained** di `local/`.
- Memungkinkan AI-assisted pre-prepare dengan status file.
- Memisahkan eksperimen lokal dari pipeline GitHub.
- Menjadi dasar refactor modular (SoC, adapter/provider seam, testability).

### 5.2 Command CLI Lokal

Jalankan dari root repo:

```powershell
python local/scripts/local_workflow.py <command> [--dir local/execution] [--label ...] [--input ...]
```

| Command | Fungsi | AI/API | Catatan |
|---|---|---|---|
| `bootstrap` | Create missing/kosong `quote/youtube/config` stepwise | Ya | Tunda youtube/config jika transcript belum ready |
| `quote` | Create/verify `quote.json` status-aware | Ya | `publish` skip |
| `transcript --input <txt>` | Convert TXT -> `transcript.json` | Tidak | Hasil `draft` |
| `transcript` | Verify struktur transcript yang sudah ada | Ya | Jika segments kosong: minta input |
| `youtube` | Create/verify metadata YouTube | Ya | Butuh transcript ready; pertimbangkan konteks transkrip |
| `config` | Create/verify config render/media | Ya | Jangan halusinasi resolved media file |
| `prepare` | Resolve background/music ke `work/`, update config | API/opsional AI keyword | B3 provider seam; resume jika file ada |
| `title` (`caption` alias) | Isi title jika kosong, sync out jika ada | Ya jika kosong | Title canonical, caption legacy mirror |
| `render` | Render final video deterministik | Tidak | Butuh ffmpeg/ffprobe + file resolved |
| `archive` | Pindah execution ke `local/archive/<ts>...`, reset dari template | Tidak | Safety: exec_dir dalam local_root |
| `reset` | Reset execution dari template | Tidak | Destruktif |

### 5.3 Status Lifecycle Lokal

Status: `kosong | draft | valid | publish`.

```text
kosong --AI create/verify--> draft|valid
draft  --AI verify---------> draft|valid
valid  --AI verify/recheck-> draft|valid
valid  --manual/publish----> publish   (bookkeeping/manual; bukan auto-upload)
publish --verify command----> publish   (skip)
```

Aturan penting:
- `draft` bisa dari user atau AI.
- `valid` idealnya dikonfirmasi user setelah review.
- `publish` saat ini **bukan** bukti upload YouTube sukses.

### 5.4 Struktur Data Lokal

| File | Wajib/Inti | Catatan |
|---|---|---|
| `quote.json` | `status,id,author,language,lines,emphasis,notes` | Validator minimal: id, author, language, lines |
| `transcript.json` | `status,voiceover_file,intro_backsound_seconds,text_fade_seconds,line_reveal_interval,segments,card,...` | `segments` sumber timing/render; TXT convert -> draft |
| `youtube.json` | `status,title,description,hashtags/tags,privacy,categoryId,defaultLanguage,defaultAudioLanguage,madeForKids,...` | Title canonical; `caption*` legacy alias |
| `config.json` | `status,render,visual,audio,media,paths` | `resolved_files/resolved_file` diisi prepare |
| `vo/vo.mp3` | audio VO | path sesuai config/transcript |
| `work/*` | media resolved | `seg_bg_*.mp4`/`bg_*.mp4`, `music.mp3` |
| `out/*` | hasil render | `final.mp4`, `manifest.json`, `caption.txt`, `description.txt`, `render_info.json` |

### 5.5 Arsitektur Lokal (Saat Ini)

- **CLI:** `local/scripts/local_workflow.py`
- **Core:** `core/status.py`, `core/models.py`, `core/config_merge.py`, `core/context.py`
- **Domain:** `domain/validation.py`, `domain/transcript.py`, `domain/timing.py`, `domain/layout.py`
- **Adapters:** `adapters/ai_client.py`, `env.py`, `ffmpeg.py`, `fs.py`, `pillow_render.py`, `media_provider.py`
- **Services:** `metadata_service.py`, `prepare_service.py`, `render_service.py`, `media_pipeline.py`, `lifecycle_service.py`
- **Legacy/utils:** `ai.py`, `common.py`, `pixabay.py`, `freetouse.py`, `title_meta.py`, `vo_txt_to_transcript.py`

B3/B6 minimal yang sudah ada:
- **B3:** provider seam untuk background/music (`MediaProviderError/MediaAsset/Protocol/Registry/Bundle`), injectable resolver, mock tanpa `sys.modules`/network.
- **B6 minimal:** `ServiceContext` + `prepare_service.cmd_prepare(..., ctx=None)`; explicit ctx override global bundle.

## 6) Batas Data & Keamanan

- **Jangan commit secret:** `local/.env`, root `.env`, token, API key.
- **Gunakan `.env.example`** sebagai template.
- **GitHub Secrets/Vars** hanya untuk workflow CI.
- **Data cache/log GitHub** (`data/*.jsonl`) boleh berubah oleh workflow CI; jangan campur dengan eksperimen lokal sembarangan.
- **Archive/reset lokal destruktif/berpindah**: pastikan path di dalam `local_root`.

## 7) Status Terkini (Known Good / Known Issues)

### 7.1 Terverifikasi

- Test lokal: `python -m unittest discover -s local/tests -p "test_*.py"` → **54 tests, OK** (saat snapshot ini).
- Render mock regression: `local/tests/unit/test_render_service_mock.py` OK.
- Provider seam B3: `local/tests/unit/test_media_provider.py` OK.
- Context isolation B6 minimal: `local/tests/unit/test_service_context_isolation.py` OK.
- End-to-end lokal pernah dijalankan dan dilaporkan di `local/docs/execution-report-2026-11-22.md`; output final terakhir terverifikasi ffprobe: `final.mp4` 65.37s, 1080x1920, card 58.164–64.364s.

### 7.2 Celah Terbuka Prioritas

| ID | Prioritas | Celah | Dampak | Arah patch |
|---|---|---|---|---|
| O5 | High | AI youtube.json belum mengisi semua field kosong tanpa overwrite user | Metadata tidak lengkap | Extend `cmd_youtube`/validation: fill-empty-only + field profile + tests |
| O1/O7 | High | Render timeout/korup bisa lolos tanpa gate ffprobe keras | MP4 invalid dianggap sukses | Post-render ffprobe gate wajib; fail/cleanup/quarantine |
| O3/O13 | Med | `publish` ambigu; belum ada upload YouTube eksplisit | Status menyesatkan | Pisah `rendered/ready_to_publish/published` atau metadata upload |
| O6 | Med | `youtube_is_complete` terlalu minimal | `valid` bisa false positive | Strict/minimal completeness profile |
| O4/B6 | Med | Module-global `init_context` masih luas | Testability/isolation terbatas | Lanjutkan explicit ServiceContext ke semua services |
| O2/O14 | Med | Risiko regresi split render/prepare | Crash runtime | Audit simbol + integration tests ffmpeg-mocked |

## 8) Cara Memakai Dokumen Ini di Sesi Baru

Di sesi baru, minta agent:

1. Baca `docs/PROJECT_CONTEXT.md` ini dulu.
2. Identifikasi apakah tugas menyentuh **GitHub workflow** atau **lokal**.
3. Jangan mengubah GitHub workflow jika tugas lokal, kecuali diminta.
4. Jalankan verifikasi relevan (`unittest`, ffprobe, command CLI) sebelum menyimpulkan sukses.
5. Laporkan file yang diubah, risiko, dan celah yang belum ditutup.

Prompt singkat yang bisa dipakai user:

```text
Baca docs/PROJECT_CONTEXT.md. Pahami pemisahan workflow GitHub vs lokal. Kerjakan tugas berikut tanpa mengubah GitHub workflow kecuali saya minta: <tugas>.
```

## 9) Referensi Cepat

- Workflow GitHub: `.github/workflows/shorts.yml`
- Plan/render/publish CI: `scripts/plan.py`, `scripts/render.py`, `scripts/publish.py`
- CLI lokal: `local/scripts/local_workflow.py`
- Status lokal: `local/scripts/core/status.py`
- Metadata lokal: `local/scripts/services/metadata_service.py`
- Prepare lokal: `local/scripts/services/prepare_service.py`
- Render lokal: `local/scripts/services/render_service.py`
- Provider seam: `local/scripts/adapters/media_provider.py`
- Context seam: `local/scripts/core/context.py`
- Env lokal: `local/.env.example`
- Laporan eksekusi lokal: `local/docs/execution-report-2026-11-22.md`
- Panduan lokal: `local/README.md`
