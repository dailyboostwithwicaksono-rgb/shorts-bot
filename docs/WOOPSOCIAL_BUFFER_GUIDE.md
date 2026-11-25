# Panduan publish tanpa Google OAuth: WoopSocial + Buffer

Dokumen ini menjelaskan dua jalur publish berbasis **API key** yang dipakai workflow utama `shorts-bot`, kapan Google OAuth masih diperlukan, dan cara menjalankan/ menguji masing-masing target.

## 1. Ringkasan: apa yang masih butuh Google OAuth?

| Kebutuhan | Jalur saat ini | Google OAuth? | Catatan |
|---|---|---|---|
| YouTube Shorts | `scripts/publish_youtube.py` (target `youtube`) | **Ya** (`YT_REFRESH_TOKEN`) | Bisa diganti Buffer hanya jika channel YouTube dihubungkan di Buffer dan `BUFFER_SERVICES` ditambah `youtube`. Saat ini **belum** ada channel YouTube di Buffer. |
| Instagram Reels + TikTok | `scripts/publish_woopsocial.py` (target `woopsocial`) | Tidak | Memakai `WOOPSOCIAL_API_KEY`, publish langsung (`PUBLISH_NOW`). |
| Facebook Page + Threads | `scripts/publish_buffer.py` (target `buffer`) | Tidak | Memakai `BUFFER_API_KEY`, publish langsung (`shareNow`). Upload media memakai `GITHUB_TOKEN`, bukan Google. |
| Arsip file ke Google Drive | `scripts/archive_drive.py` | **Ya** (`YT_*` OAuth user) | **Opsional.** Bisa dimatikan dengan repository variable `ARCHIVE_DRIVE=0`. Tidak ada pengganti API untuk arsip ini; file tetap ada di `out/` pada runner selama run berjalan. |

**Kesimpulan:** WoopSocial + Buffer benar-benar menggantikan Google OAuth untuk publish ke IG/TikTok/Facebook/Threads. Google OAuth masih diperlukan bila Anda tetap publish ke YouTube dan/atau mengarsipkan ke Drive. Untuk alur tanpa OAuth sama sekali: matikan arsip Drive (`ARCHIVE_DRIVE=0`) dan hapus `youtube` dari `PUBLISH_TARGETS` di `.github/workflows/shorts.yml` (saat ini di-hardcode `youtube,woopsocial,buffer`), atau hubungkan channel YouTube ke Buffer terlebih dahulu.

## 2. Kredensial & konfigurasi

Semua kunci hanya boleh disimpan sebagai **GitHub Repository Secret** dan/atau `.env` lokal yang ter-ignore. Jangan pernah menaruh kunci di repo, log, atau chat. Kunci yang pernah tampil di chat sebaiknya di-rotate.

| Secret GitHub | Fungsi | Wajib untuk |
|---|---|---|
| `WOOPSOCIAL_API_KEY` | Auth API WoopSocial (`https://api.woopsocial.com/v1`) | target `woopsocial` |
| `BUFFER_API_KEY` | Auth GraphQL Buffer (`https://api.buffer.com`, header `Bearer`) | target `buffer` |
| `GITHUB_TOKEN` | Otomatis tersedia; dipakai untuk upload video ke GitHub Release asset | target `buffer` |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | Google OAuth user | target `youtube` + arsip Drive |
| `GDRIVE_OUTPUTS_FOLDER_ID` | Folder tujuan arsip | arsip Drive |

Repository variables yang dipakai (opsional): `ARCHIVE_DRIVE` (default `1`; set `0` untuk melewati arsip Drive), `PUBLISH_DRY_RUN`, `PUBLISH_FAIL_FAST`, `BUFFER_FACEBOOK_POST_TYPE` (default `reel`). Target default `youtube,woopsocial,buffer` dan ID akun/project sudah di-hardcode di workflow agar tidak bergantung pada variable yang salah ketik. Untuk **manual run** yang hanya ingin mengulang sebagian, isi input `publish_targets` (mis. `buffer`) agar target lain tidak publish dobel.

## 3. WoopSocial (Instagram Reels + TikTok)

- Akun/project utama: project `199149673229844480` (`dailyboostwithwicaksono@gmail.com's business`).
- **Channel:** IG `dailyboostwithwicaksono` (`199150343760642048`), TikTok `dailyboostwithwicaksono` (`199150530960818176`), keduanya `CONNECTED`.
- Metadata (judul, deskripsi, hashtag, `link: -`) diambil dari artefak kanonik `out/manifest.json`, bukan generate ulang.
- Perilaku: upload video lalu **`PUBLISH_NOW`** — tanpa penjadwalan.

### Uji dry-run (tidak membuat post)

```powershell
$env:PUBLISH_TARGETS='woopsocial'; $env:PUBLISH_DRY_RUN='1'; python scripts/publish.py
```

Dry-run WoopSocial tetap meng-upload video atau media uji untuk keperluan `posts_validate`, tetapi **tidak membuat post**. Log ada di `work/woopsocial/`.

### Publish nyata

Dijalankan otomatis oleh Actions lewat `PUBLISH_TARGETS: youtube,woopsocial,buffer`, atau manual:

```powershell
$env:PUBLISH_TARGETS='woopsocial'; $env:PUBLISH_DRY_RUN='0'; python scripts/publish.py
```

Log yang diharapkan:

```text
[info] WoopSocial target: INSTAGRAM:dailyboostwithwicaksono, TIKTOK:dailyboostwithwicaksono
[info] Ringkasan publish: 2 target, 0 gagal
```

Masalah umum: `401/403` berarti kunci salah/perlu di-rotate; `tidak ada akun ... yang CONNECTED` berarti project/akun berubah di dashboard WoopSocial (ID harus ditulis sebagai string, bukan angka tanpa tanda kutip di YAML).

## 4. Buffer (Facebook Page + Threads)

- Endpoint: `POST https://api.buffer.com` (GraphQL), auth `Authorization: Bearer BUFFER_API_KEY`.
- Organisasi: `My Organization` → `67966ea2f0cdace9b4192336`.
- Channel aktif: Facebook Page `Daily Boost with Wicaksono` → `6b0703908541f09ecb9ebcea`; Threads `dailyboostwithwicaksono` → `6b0709f78541f09ecb9f594a`.
- Resolusi channel dilakukan otomatis lewat `BUFFER_SERVICES=facebook,threads`, jadi ID tidak perlu di-hardcode di kode.
- Perilaku: `schedulingType: automatic`, `mode: shareNow` (publish langsung). Kuota harian Facebook = 35 post, jadi 5x/hari aman.
- Facebook wajib membawa `metadata.facebook.type`; default `reel` (video 9:16), bisa diganti lewat `BUFFER_FACEBOOK_POST_TYPE` (`post`/`reel`/`story`).
- Teks: Facebook memakai `title + description` lengkap (maks 2200 karakter); Threads memakai `title + description` yang dipotong aman di 500 karakter. `manifest.caption` adalah alias judul dari `plan.py`, jadi **tidak** dipakai sebagai isi deskripsi — penyebab caption Threads sebelumnya hanya judul yang terulang.

### Media: wajib URL publik

Buffer **tidak memiliki endpoint upload**. `assets[].video.url` harus HTTPS publik, langsung ke file MP4, dan tetap bisa diambil sampai post dipublish. Link Google Drive **tidak memenuhi** (halaman preview/login, bukan direct file).

Jalur yang dipakai `scripts/publish_buffer.py`:

1. Buat/pakai GitHub Release dengan tag `BUFFER_RELEASE_TAG` (default `media`).
2. Upload `out/final.mp4` sebagai asset dengan nama unik memakai `GITHUB_TOKEN`.
3. Pakai `browser_download_url` dari GitHub sebagai `assets[].video.url`.
4. Verifikasi URL bisa diakses publik sebelum `createPost`.
5. Bersihkan asset yang lebih tua dari `BUFFER_ASSET_TTL_HOURS` (default 6 jam).

Repo `shorts-bot` bersifat public sehingga URL `releases/download/...` bisa diakses tanpa login. Alternatif: isi `BUFFER_VIDEO_URL` dengan URL permanen milik sendiri untuk melewati upload Release.

### Uji dry-run (tidak upload, tidak membuat post)

```powershell
$env:PUBLISH_TARGETS='buffer'; $env:PUBLISH_DRY_RUN='1'; python scripts/publish.py
```

Contoh hasil:

```text
[info] Publish buffer: dry-run (2 channel valid, 0 post dibuat (facebook:Daily Boost with Wicaksono, threads:dailyboostwithwicaksono))
[info] Ringkasan publish: 1 target, 0 gagal
```

Log payload ada di `work/buffer_*.json` (tanpa token).

### Publish nyata

```powershell
$env:PUBLISH_TARGETS='buffer'; $env:PUBLISH_DRY_RUN='0'; $env:GH_TOKEN='<PAT dengan izin repo>'; python scripts/publish.py
```

Di GitHub Actions, `GH_TOKEN` diambil otomatis dari `secrets.GITHUB_TOKEN`. Bila sebagian target sudah sukses lalu run gagal di target lain, jalankan ulang lewat *Run workflow* dengan input `publish_targets=buffer` agar YouTube/WoopSocial/Threads tidak terbit lagi. Log yang diharapkan:

```text
[ok] Buffer facebook: post <id> status=sending
[ok] Buffer threads: post <id> status=sending
[info] Ringkasan publish: 2 target, 0 gagal
```

### Masalah umum Buffer

| Gejala | Penyebab / penanganan |
|---|---|
| `401 Unauthorized` | `BUFFER_API_KEY` salah/ter-rotate. Perbarui Secret GitHub. |
| `channel ... belum terhubung; dilewati` | Channel belum di-add di Buffer UI, atau nama di `BUFFER_SERVICES` salah. Tambahkan channel lalu jalankan ulang. |
| `URL media tidak bisa diakses publik` | Host tidak direct/HTTPS atau repo private. Pakai Release asset dari repo public, atau `BUFFER_VIDEO_URL` yang benar-benar publik. |
| `InvalidInputError: Facebook posts require a type (post, story, or reel)` | Payload Facebook belum punya `metadata.facebook.type`. Sudah ditambahkan; default `reel`. Cek `BUFFER_FACEBOOK_POST_TYPE` bila diubah ke nilai di luar daftar. |
| Caption Threads/Facebook hanya mengulang judul | `manifest.caption` memang alias judul. Publisher sekarang mengambil `manifest.description` sebagai isi; Facebook ~2200 char, Threads 500 char. |
| `needs_approval` | Channel mengharuskan approval; buka Buffer UI dan setujui post. API tetap menyimpan post sebagai draft. |
| `429 Too Many Requests` | Penuhi `Retry-After`; kurangi frekuensi atau gunakan jadwal Buffer. |
| Video 9:16 di Facebook | Dikirim sebagai `metadata.facebook.type: reel` (default), sehingga tampil sebagai Reel. |

## 5. Melewati arsip Google Drive

Arsip Drive berjalan di langkah terpisah dan tidak memengaruhi publish. Untuk mematikannya:

1. Di GitHub → *Settings → Secrets and variables → Actions → Variables*, buat variable **`ARCHIVE_DRIVE`** dengan nilai `0`.
2. Jalankan workflow seperti biasa. Langkah *Arsipkan hasil ke Drive* akan dilewati; `YT_*` tetap diperlukan hanya jika target `youtube` aktif.

Konsekuensi: tidak ada salinan permanen di Drive. Simpan `out/final.mp4` secara manual bila diperlukan, atau biarkan GitHub Release asset Buffer (dengan TTL 6 jam) sebagai salinan sementara.

## 6. Checklist sebelum mengaktifkan target baru

- [ ] Secret `BUFFER_API_KEY` / `WOOPSOCIAL_API_KEY` sudah terpasang dan valid.
- [ ] Kunci yang pernah tampil di chat sudah di-rotate.
- [ ] Dry-run per target lolos (`PUBLISH_DRY_RUN=1`).
- [ ] Channel Buffer `facebook` + `threads` masih `CONNECTED`.
- [ ] `PUBLISH_FAIL_FAST` dipahami: default `1` membuat run berhenti saat satu target gagal.
- [ ] Konten siap dipublikasikan publik (ireversibel).
