# SnipSimpan

Aplikasi screenshot (PySide6) yang **langsung menyimpan gambar ke folder pilihan Anda**, tanpa dialog "Save As".
Tekan hotkey berkali-kali, file baru terus masuk ke folder itu.
Bisa juga menerima **foto dari kamera HP** lewat browser, tanpa perlu memasang aplikasi di HP.

## Unduh

Cara paling mudah: unduh **`SnipSimpan.exe`** dari halaman
[Releases](https://github.com/nauyand/snip-simpan/releases/latest), lalu jalankan. Tidak perlu memasang Python.

## Cara pasang dari kode sumber (Windows)

1. Pasang Python 3.9 atau lebih baru dari https://www.python.org/downloads/ (centang **Add Python to PATH**).
2. Klik dua kali **`install.bat`**. Cukup sekali, untuk memasang PySide6 dan segno (pembuat QR code).
3. Klik dua kali **`jalankan.bat`** untuk membuka aplikasi.

Atau lewat terminal:

```
pip install PySide6 segno
python snipsimpan.py
```

Ingin membuat file `.exe` sendiri? Jalankan **`buat_exe.bat`**, hasilnya ada di `dist\SnipSimpan.exe`.
Ikon aplikasi (`snipsimpan.ico`) dibuat ulang otomatis oleh `buat_icon.py` dari ikon yang digambar di `snipsimpan.py`.

## Cara pakai

1. Tab **Screenshot**: klik **Pilih…** untuk menentukan folder tujuan.
2. Ambil screenshot lewat tombol atau hotkey. File langsung tersimpan.

| Aksi | Hotkey default | Keterangan |
|---|---|---|
| Layar penuh | `Ctrl+Alt+1` | Monitor tempat kursor berada (bisa diubah ke semua monitor atau monitor utama) |
| Pilih area | `Ctrl+Alt+2` | Seret untuk memilih area seperti di Snipping Tool. Esc atau klik kanan untuk batal |
| Ulangi area terakhir | `Ctrl+Alt+3` | Area yang sama tersimpan lagi tanpa perlu menyeret ulang. Cocok untuk screenshot berulang |
| Jendela aktif | `Ctrl+Alt+4` | Hanya jendela yang sedang dipakai |
| Mulai / stop otomatis | `Ctrl+Alt+5` | Screenshot otomatis setiap N detik |

### Mengganti hotkey
Buka tab **Hotkey**, klik kolomnya, lalu tekan kombinasi yang Anda mau.
- **Esc** membatalkan, **Backspace** menonaktifkan hotkey.
- Status **✓ Aktif** berarti hotkey siap dipakai, walaupun jendela aplikasi tersembunyi.
- Status **Sudah dipakai aplikasi lain** berarti kombinasi itu bentrok. Pilih kombinasi lain.
- Ingin memakai tombol **PrintScreen**? Di Windows 11 matikan dulu pengaturan
  *Settings → Accessibility → Keyboard → "Use the Print screen key to open screen capture"*.

### Nama file
Atur di tab **Pengaturan → Pola nama**. Kode yang bisa dipakai:

- `{tanggal}`: 2026-11-16
- `{jam}`: 14-30-05
- `{nomor}`: 0001, 0002, … (nomor urut, bisa di-reset)
- `{mode}`: layar / area / jendela / kamera
- `{proyek}`: nama proyek yang sedang aktif (kosong di mode Normal)

Contoh pola: `Laporan_{nomor}` menghasilkan `Laporan_0001.png`, `Laporan_0002.png`, dan seterusnya.
Jika ada nama yang sama, aplikasi otomatis menambahkan `_2`, `_3`, dan seterusnya, jadi tidak ada file yang tertimpa.

Pilihan lain: format PNG atau JPG, subfolder per tanggal, jeda sebelum mengambil, salin ke clipboard, notifikasi, dan bunyi.

### Proyek (subfolder pilihan sendiri)
Kelompokkan screenshot berdasarkan pekerjaan, bukan tanggal.

1. Di tab **Screenshot**, klik **+ Proyek baru**, lalu beri nama, misalnya `Project A`.
2. Selama proyek itu aktif, semua screenshot **dan foto dari HP** masuk ke `…\folder penyimpanan\Project A\`.
   Judul jendela dan tooltip tray menampilkan proyek yang sedang aktif.
3. Selesai? Pilih **Normal (tanpa proyek)** dan penyimpanan kembali seperti biasa
   (langsung di folder, atau per tanggal jika opsi subfolder per tanggal dicentang).

Proyek bisa diganti cepat lewat menu tray **Proyek: …**, tanpa membuka jendela. Daftar proyek tetap tersimpan,
jadi nanti tinggal dipilih lagi. Tombol **✕** hanya menghapus proyek dari daftar; folder dan filenya tidak ikut terhapus.

### Kamera HP (tanpa aplikasi di HP)
Foto dengan kamera HP, hasilnya langsung masuk ke folder yang sama di PC.

1. Pastikan HP dan PC tersambung ke **Wi-Fi yang sama**.
2. Buka tab **Kamera HP**, lalu klik **Aktifkan**. Jika Windows Firewall bertanya, izinkan untuk jaringan **Private**.
3. Scan QR code yang muncul dengan kamera HP, atau ketik alamatnya (mis. `http://192.168.1.10:8765/?k=…`) di browser HP.
4. Tekan **📷 Ambil Foto**. Kamera bawaan HP terbuka; setelah foto diambil, file langsung terkirim dan tersimpan.
   Tombol **🖼️ Kirim dari Galeri** bisa mengirim beberapa foto sekaligus.

Catatan:
- Foto disimpan dalam format aslinya dari HP (biasanya JPG, resolusi penuh, tanpa kompres ulang). Nama file memakai
  pola tersendiri (default `Foto_{tanggal}_{jam}`).
- Alamat memakai **kode akses** acak, jadi orang lain di Wi-Fi yang sama tidak bisa mengirim file tanpa QR/alamat itu.
  Klik **Ganti kode** untuk membatalkan akses HP lama.
- HP tidak bisa membuka alamatnya? Pastikan profil Wi-Fi di Windows adalah *Private* (bukan *Public*), atau pilih alamat
  lain di daftar **Alamat PC** (PC dengan VPN/VirtualBox bisa punya beberapa alamat).
- Centang **Aktifkan otomatis** agar server kamera langsung siap setiap kali SnipSimpan dibuka. Bisa juga dinyalakan
  dari menu tray.

### Tray
Tombol **X** menyembunyikan aplikasi ke system tray (ikon biru di dekat jam), dan hotkey tetap aktif.
Untuk benar-benar menutup aplikasi: klik kanan ikon tray, lalu pilih **Keluar**.

Pengaturan tersimpan di `%LOCALAPPDATA%\SnipSimpan\config.json`.
