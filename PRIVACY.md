# Kebijakan Privasi — shorts-bot

Terakhir diperbarui: 2026-11-19

Kebijakan privasi ini menjelaskan bagaimana aplikasi **shorts-bot** (proyek otomatisasi pribadi yang dikelola di repositori ini) mengakses dan memproses data saat digunakan oleh pemilik akun.

## 1. Tujuan aplikasi
**shorts-bot** adalah alat otomatisasi pribadi untuk:
- membuat video YouTube Shorts (quotes) dari konten dan media yang dikonfigurasi,
- mengunggah video ke channel YouTube milik pemilik akun, dan
- membaca/menyimpan file pendukung di Google Drive milik pemilik akun (misalnya mengambil musik dan mengarsipkan hasil render).

Aplikasi ini dijalankan oleh pemilik repositori/akun (misalnya melalui GitHub Actions) untuk keperluan penggunaan pribadi.

## 2. Data yang diakses
Dengan izin (OAuth) dari pemilik akun, aplikasi dapat mengakses:
- **YouTube** (scope unggah, mis. `https://www.googleapis.com/auth/youtube.upload`): untuk mengunggah video dan metadata (judul, deskripsi, tag, status privasi) ke channel YouTube milik pemilik akun.
- **Google Drive** (scope `https://www.googleapis.com/auth/drive`): untuk membaca file yang diperlukan proses (mis. musik latar) dan membuat/mengunggah file arsip hasil (video, manifest, caption) ke folder Google Drive milik pemilik akun.
- **Data konfigurasi & konten repositori**: daftar quotes, pengaturan tema/media, dan log pemakaian yang disimpan di repositori sesuai konfigurasi pemilik.

Aplikasi **tidak** dimaksudkan untuk mengakses data milik pengguna lain.

## 3. Cara penggunaan dan pemrosesan data
- Data digunakan hanya untuk menjalankan fungsi otomatisasi di atas (menghasilkan video, mengarsipkan, dan mengunggah ke akun milik pemilik).
- Proses dapat berjalan di lingkungan eksekusi yang dikonfigurasi pemilik (mis. GitHub Actions runner). Kredensial/token akses disimpan sebagai rahasia konfigurasi (mis. GitHub Secrets) oleh pemilik dan digunakan untuk memanggil API Google yang relevan.
- Aplikasi tidak menjual data pribadi.

## 4. Berbagi data kepada pihak ketiga
- Data tidak dibagikan atau dijual kepada pihak ketiga untuk tujuan pemasaran.
- Data dikirim ke layanan pihak ketiga hanya sejauh diperlukan untuk menjalankan fungsi aplikasi, antara lain **Google API** (YouTube Data API, Google Drive API) dan layanan infrastruktur yang dipilih pemilik untuk menjalankan otomatisasi (mis. GitHub Actions). Penggunaan layanan tersebut tunduk pada kebijakan masing-masing penyedia.

## 5. Penyimpanan dan keamanan
- Token/kredensial akses sebaiknya disimpan sebagai secret di lingkungan pemilik (bukan dalam kode sumber publik).
- File hasil dan log disimpan sesuai konfigurasi pemilik (mis. di Google Drive milik pemilik dan/atau di repositori).
- Pemilik bertanggung jawab atas pengelolaan akses ke akun Google, repositori, dan secret yang digunakan.

## 6. Hak dan kontrol pemilik akun
Pemilik akun dapat:
- **Mencabut akses** aplikasi kapan saja melalui pengaturan akun Google: [https://myaccount.google.com/permissions](https://myaccount.google.com/permissions).
- Menghapus atau memutar (rotate) token/secret yang tersimpan di konfigurasi (mis. GitHub Secrets).
- Menghapus file arsip/log yang dihasilkan di Google Drive atau repositori milik sendiri.

## 7. Anak-anak
Aplikasi ini tidak ditujukan untuk anak-anak dan tidak dirancang untuk mengumpulkan data pribadi anak-anak.

## 8. Perubahan kebijakan
Kebijakan privasi ini dapat diperbarui dari waktu ke waktu. Tanggal "Terakhir diperbarui" akan disesuaikan jika ada perubahan.

## 9. Kontak
Untuk pertanyaan terkait privasi atau penggunaan aplikasi ini, silakan hubungi pemilik repositori melalui halaman repositori: [https://github.com/dailyboostwithwicaksono-rgb/shorts-bot](https://github.com/dailyboostwithwicaksono-rgb/shorts-bot).
