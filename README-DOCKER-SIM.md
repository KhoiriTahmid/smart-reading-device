# Smart Reading Device — Docker Simulator

Simulator ini menjalankan **kode asli** Raspberry Pi (`main.py` dan seluruh modul `helper/*`), namun perangkat keras fisik (GPIO, kamera CSI/USB, motor H-bridge, kipas pembalik halaman, tombol, dan speaker) dijalankan dalam lingkungan terisolasi menggunakan **Docker**.

## 1. Keuntungan Menggunakan Docker
- **Kode Asli Berjalan Penuh**: Menjalankan alur event thread, polling queue, state machine `loop(pi)`, dan komunikasi WebSocket Cloud yang persis sama dengan Raspberry Pi fisik.
- **Aman & Terisolasi**: Tidak menyentuh hardware fisik nyata, aman dijalankan di laptop tanpa khawatir risiko mekanikal pada motor atau kipas.
- **Logging Transparan**: Setiap status kipas (`FAN`), pergerakan motor (`IN3/IN4/ENB`), lampu kamera (`LED`), serta suara speaker (`aplay/mpg123`) ditampilkan secara jelas di terminal dengan ikon visual.

---

## 2. Cara Menjalankan Simulator

### Cara A: Menjalankan Langsung dengan `docker run` (Interaktif)
Jalankan perintah berikut di terminal Anda:

```bash
docker run --rm -it --network host \
  -e DEVICE_SERIAL=SR-RPI4-001 \
  -e DEVICE_API_KEY=sr_5d8a6c20601dd09704e65ab0f713576378a16c2bfd50430b \
  smart-reading-device-sim
```

### Cara B: Menggunakan Docker Compose
```bash
DEVICE_SERIAL=SR-RPI4-001 \
DEVICE_API_KEY=sr_5d8a6c20601dd09704e65ab0f713576378a16c2bfd50430b \
docker compose -f docker-compose.sim.yml run --rm smart-reading-device
```

---

## 3. Kontrol Tombol Fisik Virtual di Terminal

Saat container berjalan, Anda dapat menekan tombol berikut di terminal untuk mensimulasikan interaksi fisik pada alat:

| Tombol Terminal | Komponen Fisik yang Disimulasikan | Efek Log / Aksi |
|---|---|---|
| `[Enter]` atau `[s]` | **Tombol Scan / Mulai (BTN5)** | Memicu potret kamera kiri (Hal 1) & kanan (Hal 2), membungkus jadi PDF, mengirim ke Cloud OCR+TTS, lalu memutar motor maju & menyalakan kipas |
| `[1]` | **Sakelar Power Utama (SW1)** | Menghidupkan/mematikan alat (ON / OFF) dengan prosedur homing otomatis |
| `[l]` | **Sakelar Bahasa (SW2)** | Mengubah bahasa OCR & Suara antara Bahasa Indonesia dan English |
| `[+]` / `[-]` | **Knob Volume (KY-040 #1)** | Menaikkan / menurunkan volume speaker virtual |
| `[>]` / `[<]` | **Knob Kecepatan TTS (KY-040 #2)** | Mengatur kecepatan bacaan suara |
| `[h]` | **Limit Switch Home (LIMIT_SW1)** | Mensimulasikan posisi motor telah kembali ke pangkal/home |
| `[f]` | **Limit Switch Flip (LIMIT_SW2)** | Mensimulasikan pembalik halaman buku selesai |
| `[?]` | **Menu Bantuan** | Menampilkan daftar perintah kontrol |
| `[q]` | **Keluar** | Menghentikan container simulator |

---

## 4. Contoh Tampilan Log di Terminal

```text
2026-11-12 13:21:53 [cloud-ws] helper.cloud_client: INFO: Connected to Smart Reading Cloud WebSocket
📸 [SIM CAM] Memotret Kamera Kiri (Halaman 1) & Kanan (Halaman 2)...
💡 [LED  GPIO18] ON  — lampu kamera menyala
💡 [LED  GPIO18] OFF
2026-11-12 13:21:55 [ocr_tts_worker] helper.ocr_tts: INFO: Uploaded 2-page PDF to cloud: historyId=...
🔊 [SPEAKER ALAT] (sim) Membacakan hasil TTS: '/tmp/cloud_tts_p1.wav' (volume=80%)
⚙️  [MOTOR ENB GPIO12] BERGERAK MAJU (forward) — PWM 255/255
🌀 [FAN  GPIO26] ON  — kipas pembalik halaman BERPUTAR
```
