# Panduan Integrasi Publish: TikTok, Meta (Instagram/Facebook), dan X

> **Status penting (baca dulu):** dokumen ini adalah panduan **bertahap dan konservatif** untuk menyiapkan integrasi publish otomatis ke platform tambahan di atas kerangka yang sudah ada di repo ini (`scripts/publish.py` dispatcher, `PUBLISH_TARGETS`, formatter/stub). Saat ini publish **nyata** untuk TikTok/Meta/X **belum diimplementasikan** di kode (tersedia formatter + dry-run); implementasi API dilakukan bertahap setelah akses disetujui.
>
> **Kebijakan & produk platform berubah sering.** Selalu verifikasi langkah, izin/scope, batasan, dan persyaratan review di dokumentasi resmi terbaru sebelum eksekusi. Jangan menganggap panduan ini sebagai jaminan approval atau stabilitas API.

## 0. Kesiapan umum (berlaku untuk semua platform)

### 0.1 Prasyarat teknis di repo ini
- Pipeline konten sudah menghasilkan artefak kanonik: `out/final.mp4`, `out/manifest.json`, `out/caption.txt`.
- Dispatcher: `python scripts/publish.py` membaca target dari `PUBLISH_TARGETS` (default `youtube`).
- Mode aman untuk verifikasi: `PUBLISH_DRY_RUN=1` (formatter/validasi tanpa upload/publish nyata).
- Kebijakan kegagalan: `PUBLISH_FAIL_FAST=1` (default, berhenti saat target gagal) atau `0` (lanjut target lain, akhiri gagal jika ada kegagalan).

### 0.2 Prinsip kepatuhan & kualitas (mengurangi risiko penolakan/limit)
- **Izin & hak cipta:** pastikan Anda memiliki hak atas konten (video, teks, musik, aset). Patuhi lisensi (mis. Pixabay/Freetouse) dan kebijakan musik/hak cipta platform.
- **Akun asli & autentik:** gunakan akun/app resmi milik Anda; hindari otomasi yang melanggar ketentuan platform (spam, perilaku tidak autentik, misleading metadata).
- **Privasi & data:** simpan token/secret hanya di secret manager (GitHub Secrets/`.env` lokal yang tidak di-commit). Rotasi jika bocor.
- **Uji bertahap:** mulai dari akun uji/sandbox (jika tersedia), dry-run, lalu publish manual/uji terbatas sebelum otomatis penuh.

### 0.3 Potensi kegagalan umum (lintas platform)
| Kategori | Contoh gejala | Penyebab umum | Mitigasi |
|---|---|---|---|
| Akses/app belum disetujui | error permission/unauthorized, endpoint tidak tersedia | App belum direview/approved, produk/API belum diaktifkan | Selesaikan verifikasi bisnis/app review; gunakan mode sandbox/tes; cek status produk di dashboard developer |
| Kredensial/token | 401/403, `invalid_grant`, token expired/revoked | Secret salah, token kedaluwarsa/dicabut, scope kurang | Validasi env, regenerate token sesuai flow resmi, pastikan scope mencukupi, rotasi secret |
| Batasan konten/format | upload rejected, processing failed | Durasi/rasio/codec/ukuran melampaui batas, caption terlalu panjang | Pastikan 1080x1920 mp4 H.264/AAC (sesuai output saat ini), patuhi batas durasi/ukuran & panjang teks per platform |
| Rate limit/quota | 429/limit errors | Terlalu sering memanggil API | Backoff/retry terkontrol, batasi frekuensi, pantau kuota |
| Review/moderasi | konten dibatasi/dihapus, publish gagal setelah processing | Pelanggaran kebijakan komunitas/musik/copyright | Pastikan konten patuh kebijakan; siapkan banding sesuai proses platform; uji manual |
| Perubahan API/kebijakan | error tak terduga, field deprecated | Versi API/produk berubah | Pin versi API bila ada, pantau changelog resmi, uji berkala |

---

## 1. TikTok (Content Posting / Direct Post API)

### 1.1 Ringkasan & rujukan resmi (wajib dicek)
- Portal developer: https://developers.tiktok.com/
- Produk/Content Posting API (referensi): https://developers.tiktok.com/products/content-posting-api/ dan dokumentasi API terkait (Direct Post). Alur, endpoint, dan nama produk dapat berubah—ikuti dokumen resmi terbaru.
- Kebijakan developer & komunitas: ikuti **TikTok Developer Terms/Policy** dan **Community Guidelines** yang berlaku.

### 1.2 Prasyarat akun & akses
- Akun TikTok yang valid (untuk pengujian; beberapa mode memerlukan akun tertentu/sandbox sesuai produk).
- Aplikasi terdaftar di TikTok for Developers.
- **Akses produk Content Posting/Direct Post**: sering memerlukan permohonan/approval dan hanya tersedia untuk use case yang diizinkan. Jangan berasumsi akses langsung tersedia.
- Redirect URI/konfigurasi app sesuai dokumentasi (untuk OAuth).
- Lingkungan uji/sandbox bila disediakan (sangat disarankan sebelum produksi).

### 1.3 Izin (scopes) — verifikasi nama scope di dokumen terbaru
Izin untuk posting konten bersifat sensitif dan bergantung produk (mis. Direct Post). Nama scope dan kombinasi yang valid dapat berbeda; contoh kategori yang umum dibutuhkan: izin dasar identitas/profil pengguna dan izin unggah/publish video. **Konfirmasi scope persis** di portal/dokumen resmi saat pembuatan app.

### 1.4 Langkah penyiapan bertahap
1. **Buat & konfigurasi app**
   - Masuk ke https://developers.tiktok.com/ → buat app.
   - Isi detail app (nama, deskripsi, ikon, website/privacy/terms bila diminta) secara akurat.
   - Tambahkan produk **Content Posting/Direct Post** (atau yang setara di UI terbaru) jika tersedia untuk akun/use case Anda.
2. **Atur redirect & platform**
   - Daftarkan Redirect URI yang akan dipakai untuk OAuth (HTTPS valid). Simpan `client_key`/`client_secret` sesuai istilah di portal.
3. **Minta/aktifkan izin yang diperlukan**
   - Pilih scope minimal yang dibutuhkan untuk posting. Catat bahwa beberapa scope memerlukan review/justifikasi.
4. **Uji di sandbox/target user yang diizinkan**
   - Gunakan akun uji yang diizinkan produk. Lakukan flow otorisasi dan uji unggah sesuai mode yang diberikan (mis. draft vs direct post) di lingkungan non-produksi bila ada.
5. **Implementasi OAuth & token (untuk publish nyata)**
   - Lakukan user authorization → tukar code menjadi access token (dan refresh token bila disediakan) sesuai flow resmi.
   - Simpan token secara aman; tangani refresh/expiry. (Implementasi token exchange/refresh **belum** ada di kode repo ini.)
6. **Implementasi unggah/publish (untuk publish nyata)**
   - Ikuti urutan API resmi (inisialisasi/upload/publish) sesuai mode (direct post/draft) dan batas format. (Belum diimplementasikan di repo; gunakan dry-run untuk verifikasi formatter.)
7. **Ajukan review/app approval (bila diwajibkan)**
   - Siapkan demo video, deskripsi use case, dan bukti kepatuhan. Tunggu persetujuan sebelum penggunaan produksi.
8. **Verifikasi dengan dry-run repo ini**
   - Set `PUBLISH_TARGETS=youtube,tiktok` dan `PUBLISH_DRY_RUN=1` lalu jalankan `python scripts/publish.py` untuk memastikan payload/caption terformat. (Tanpa dry-run & tanpa implementasi/kredensial nyata, target akan gagal dengan pesan jelas.)

### 1.5 Pemetaan ke kerangka repo ini
- Target: `tiktok` dalam `PUBLISH_TARGETS`.
- Secret (placeholder/scaffolding): `TIKTOK_ACCESS_TOKEN` (dibaca saat publish nyata; alur perolehan token & API call perlu diimplementasikan sesuai akses yang disetujui).
- Formatter: caption teks (judul/caption + hashtag) dengan batas konservatif.

### 1.6 Potensi kegagalan spesifik TikTok
- **Produk/scope tidak tersedia atau ditolak review:** use case otomatisasi posting dapat tidak memenuhi kriteria; siapkan justifikasi dan alternatif (unggah manual/draft) bila perlu.
- **Mode posting terbatas:** beberapa integrasi hanya mengizinkan unggah sebagai draft (butuh tindakan manual pengguna) tergantung izin/produk.
- **Batas media & metadata:** durasi, ukuran file, rasio, codec, atau caption melampaui ketentuan; processing gagal setelah upload.
- **Kepatuhan musik/copyright:** klaim atau pembatasan distribusi meski musik berlisensi—pastikan hak penggunaan sesuai konteks platform.
- **Token/region/account restriction:** token invalid/expired, akun tidak eligible, atau pembatasan wilayah/fitur.
- **Rate limit & perubahan endpoint:** lonjakan error 429 atau perubahan skema respons; perlukan penanganan error & pemantauan.

---

## 2. Meta (Instagram / Facebook)

### 2.1 Ringkasan & rujukan resmi (wajib dicek)
- Portal developer: https://developers.facebook.com/
- Instagram Graph API (Content Publishing): https://developers.facebook.com/docs/instagram-api/guides/content-publishing dan referensi IG User/Media terkait.
- Facebook Pages / Video publishing: https://developers.facebook.com/docs/video-api/ dan dokumentasi Page terkait.
- Izin & review: https://developers.facebook.com/docs/permissions/reference dan proses **App Review**.
- Kebijakan: Meta Platform Terms/Policies, Instagram/Facebook Community Standards & kebijakan konten/musik.

### 2.2 Prasyarat akun & aset
- Akun **Meta Developer** dan aplikasi Meta.
- **Instagram:** akun IG **Professional** (Business/Creator) yang terhubung ke **Facebook Page** (umum diperlukan untuk Graph API publishing). Konfirmasi syarat terbaru di dokumen.
- **Facebook:** Page yang Anda kelola (untuk publish ke Page) dengan peran/izin yang memadai.
- Akses fitur Content Publishing dapat memerlukan **App Review** dan mode app yang sesuai (Development/Live) serta akun/role uji.

### 2.3 Izin (scopes) — verifikasi di dokumen terbaru
Scope sensitif dan memerlukan persetujuan; set minimal yang relevan sering mencakup (contoh, nama dapat bervariasi): akses Page/IG, publikasi konten (mis. `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`/terkait) sesuai target. **Jangan menyalin daftar scope tanpa verifikasi** di Permission Reference terbaru dan sesuaikan dengan use case (IG saja vs Page).

### 2.4 Langkah penyiapan bertahap
1. **Buat app Meta**
   - Di https://developers.facebook.com/ buat app, pilih tipe yang sesuai use case. Isi kebijakan privasi, penghapusan data (jika diminta), dan detail app.
2. **Tambahkan produk yang relevan**
   - Mis. Instagram Graph API / akses ke Instagram & Facebook Login for Business sesuai kebutuhan terbaru. Hubungkan aset (Page, akun IG) di pengaturan.
3. **Konfigurasi peran & akun uji**
   - Tambahkan tester/developer/admin. Uji di mode Development dengan akun/role yang diizinkan.
4. **Dapatkan token & izin (untuk publish nyata)**
   - Lakukan OAuth flow untuk memperoleh User/Page access token dengan scope yang disetujui; pahami masa berlaku & pertukaran ke long-lived token bila diperlukan. Simpan aman. (Belum diimplementasikan di repo.)
5. **Identifikasi target publish**
   - Untuk IG: dapatkan `IG User ID` (mis. `{ig-user-id}`) dari akun IG profesional yang terhubung. Untuk Page: Page ID & token sesuai.
6. **Implementasi alur publish (untuk publish nyata)**
   - IG Reels/Video umumnya memakai alur container → publish (endpoint & parameter spesifik per jenis media); ikuti dokumen Content Publishing terbaru (hosting URL media, polling status, dll.). (Belum diimplementasikan di repo.)
7. **Ajukan App Review & siapkan Advanced Access**
   - Banyak izin memerlukan review & bukti screencast/use case nyata. Rencanakan waktu approval.
8. **Verifikasi dengan dry-run repo ini**
   - `PUBLISH_TARGETS=youtube,meta` + `PUBLISH_DRY_RUN=1` untuk cek formatter caption.

### 2.5 Pemetaan ke kerangka repo ini
- Target: `meta` dalam `PUBLISH_TARGETS`.
- Secrets (placeholder/scaffolding): `META_ACCESS_TOKEN`, `META_IG_USER_ID` (minimal untuk arah IG; kebutuhan aktual dapat bertambah, mis. Page token/ID, tergantung implementasi target).
- Formatter: caption (batas konservatif).

### 2.6 Potensi kegagalan spesifik Meta
- **Akun/asset tidak memenuhi syarat:** IG bukan Professional, tidak tertaut ke Page, atau role kurang → API menolak.
- **Izin belum di-approve (App Review):** 403/permission errors meski flow teknis benar.
- **Alur container/polling gagal:** media processing error, URL media tidak dapat diakses server Meta, format tidak didukung, atau status stuck/failed.
- **Kebijakan konten/musik:** pembatasan audio, copyright match, atau pelanggaran standar komunitas.
- **Rate limit & deprecations:** batas panggilan per app/akun dan perubahan versi Graph API; pantau deprecation schedule.
- **Token expiry/invalidasi:** token jangka pendek/long-lived kedaluwarsa atau dicabut.

---

## 3. X (Twitter)

### 3.1 Ringkasan & rujukan resmi (wajib dicek)
- Portal developer: https://developer.x.com/ (dan https://docs.x.com/)
- API v2 (posts/tweets, media upload): https://docs.x.com/x-api/introduction dan dokumentasi media upload + manage posts terbaru.
- Akses & pricing/tiers: https://developer.x.com/en/portal/products dan halaman pricing/akses terbaru (tier, batas, dan ketersediaan endpoint **dapat berubah**).
- Kebijakan: Developer Agreement/Policy, Automation rules, aturan media & konten.

### 3.2 Prasyarat akun & akses
- Akun X yang valid dan dalam keadaan baik (tidak dibatasi).
- Akun developer & **Project/App** di portal X. Tingkat akses (Free/Basic/Pro/Enterprise atau skema terbaru) menentukan endpoint, rate limit, dan kemampuan posting/media—**verifikasi paket yang Anda butuhkan**.
- Konfigurasi autentikasi app (OAuth 1.0a User Context dan/atau OAuth 2.0 dengan PKCE, tergantung endpoint & kebijakan terbaru).

### 3.3 Izin (scopes) — verifikasi di dokumen terbaru
- Untuk membaca/menulis post dan (bila didukung tier Anda) mengunggah media, pastikan scope OAuth 2.0 yang sesuai (mis. kategori `tweet.read`, `tweet.write`, `users.read`, `offline.access`, dan scope media bila terpisah) atau kredensial OAuth 1.0a yang tepat. **Konfirmasi scope & metode auth yang diterima endpoint target** di dokumen terbaru.

### 3.4 Langkah penyiapan bertahap
1. **Daftar & siapkan akses developer**
   - Buat/konfigurasi Project & App di portal. Pilih tier akses yang mendukung kebutuhan (posting + upload media video) sesuai dokumen/pricing terbaru.
2. **Konfigurasi autentikasi**
   - Aktifkan OAuth 2.0 (dengan callback URL yang valid) dan/atau OAuth 1.0a sesuai kebutuhan. Catat API Key/Secret, Client ID/Secret, dan atur permission app (read/write).
3. **Peroleh token pengguna (untuk publish nyata)**
   - Jalankan flow otorisasi pengguna untuk mendapatkan access token (+ refresh token bila OAuth 2.0). Simpan aman. (Belum diimplementasikan di repo.)
4. **Implementasi unggah media & pembuatan post (untuk publish nyata)**
   - Unggah video via endpoint media upload yang sesuai (sering chunked untuk video; endpoint & flow dapat berbeda antar versi/tier), lalu buat post yang mereferensikan media ID. Patuhi batas ukuran/durasi/format. (Belum diimplementasikan di repo.)
5. **Uji terbatas & patuhi aturan automasi**
   - Pastikan konten & frekuensi sesuai aturan automasi X; hindari duplikasi/spam.
6. **Verifikasi dengan dry-run repo ini**
   - `PUBLISH_TARGETS=youtube,x` + `PUBLISH_DRY_RUN=1` untuk cek formatter teks (batas 280 karakter, hashtag dibatasi).

### 3.5 Pemetaan ke kerangka repo ini
- Target: `x` dalam `PUBLISH_TARGETS`.
- Secrets (placeholder/scaffolding): `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` (cocok untuk pola OAuth 1.0a; implementasi nyata dapat juga memerlukan token OAuth 2.0 tergantung pilihan—sesuaikan saat implementasi).
- Formatter: teks post ringkas (≤280) dengan hashtag terbatas; video diunggah terpisah pada API nyata.

### 3.6 Potensi kegagalan spesifik X
- **Tier/akses tidak mencakup endpoint:** posting atau media upload gagal/forbidden karena paket tidak mendukung.
- **Auth/scope mismatch:** 401/403 karena metode auth atau scope tidak sesuai endpoint.
- **Batas media & teks:** video terlalu besar/panjang/format tidak didukung; teks melebihi 280 karakter (formatter repo memotong, namun konten akhir tetap harus sesuai).
- **Aturan automasi & pembatasan akun:** post ditandai/ditolak karena perilaku otomatis, duplikasi, atau pembatasan akun.
- **Rate limit:** 429; perlu throttling/backoff.
- **Perubahan produk/API:** endpoint atau persyaratan akses berubah; wajib pantau dokumentasi & changelog resmi.

---

## 4. Cara menguji kerangka di repo ini (aman, tanpa publish nyata)
1. Pastikan artefak render ada (`out/final.mp4`, `out/manifest.json`).
2. Dry-run semua target yang diinginkan:
   - PowerShell: `$env:PUBLISH_TARGETS='youtube,tiktok,meta,x'; $env:PUBLISH_DRY_RUN='1'; python scripts/publish.py`
3. Untuk uji gagal-parsial (terkontrol): set `PUBLISH_FAIL_FAST=0` (hanya relevan saat bukan dry-run/ada kegagalan nyata).
4. **Jangan** mengaktifkan publish nyata ke platform baru sebelum: akses/approval disetujui, kredensial valid, implementasi API selesai & diuji terisolasi, dan kepatuhan konten terverifikasi.

## 5. Checklist sebelum implementasi publish nyata per platform
- [ ] Akses produk/API & (bila perlu) app review disetujui
- [ ] Akun/aset memenuhi syarat (IG Professional+Page, Page, tier X, dll.)
- [ ] Scope/izin minimal & terverifikasi
- [ ] Token/secret tersimpan aman & mekanisme refresh/expiry jelas
- [ ] Batas format/durasi/ukuran/caption sesuai (output repo: 1080x1920 mp4)
- [ ] Kepatuhan hak cipta/musik/kebijakan komunitas
- [ ] Uji: dry-run → uji manual/sandbox → rilis terbatas → otomatis
- [ ] Penanganan error, logging, dan pemantauan rate limit/kegagalan

## 6. Referensi resmi (titik awal)
- TikTok Developers: https://developers.tiktok.com/
- Meta for Developers: https://developers.facebook.com/ (Instagram Graph API, Permissions, App Review)
- X Developer: https://developer.x.com/ dan https://docs.x.com/
- Lisensi aset yang dipakai repo: Pixabay, Freetouse (https://freetouse.com/license) — patuhi juga kebijakan platform tujuan.
