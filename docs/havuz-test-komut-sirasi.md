# İSAS Havuz Testi — Forward Only (2026-08-02)

25 m × 10 m × 2,2 m havuz · Pixhawk 2.4.8/B-Cube · ArduSub 4.7 ·
`FRAME_CONFIG=1` Vectored · Raspberry Pi · 1500 µs nötr çift yönlü ESC.

## Şu an ne olacak?

| Konu | Durum |
|---|---|
| Dikey motorlar | **İptal** (M4 yandı, M3 taşındı) |
| Tam görev / çember / dönüş | **İptal** (şimdilik) |
| Yatay ileri | **Aktif** — 4 motor |
| M3 | Eski **M6 yeri**ne takıldı → **MAIN OUT 4** |

Bu araçta fiziksel ileri yön: **`forward` negatif**. Tam güç = **`-1000`**.

## Güncel kablo / ESC

| MAIN OUT | Mantıksal | Fiziksel | Konum | ESC (kayıt) |
|---|---:|---|---|---|
| 1 | Motor1 | M1 | Sol ön, 45° yatay | Reversed / CCW |
| 2 | Motor2 | M2 | Sağ ön, 45° yatay | Reversed / CCW |
| 3 | Motor3 | M5 | Sol arka, 45° yatay | Normal / CW |
| 4 | Motor4 | **M3 (taşındı)** | Sağ arka, 45° yatay | Normal / CW |
| 5 | Motor5 | boş | eski dikey | — |
| 6 | Motor6 | yanmış M4 | eski dikey | — |

Pixhawk fonksiyonları değişmedi (`SERVO1..6_FUNCTION = 33..38`). Yazılım hâlâ
mantıksal Motor4'e komut verir; o kanala artık fiziksel M3 bağlıdır.

Taşınan M3 ESC yönü eski M6 ile aynı kayıttaydı (Normal/CW). Su içinde
`pool-motor 4` ile doğrula; ters itiyorsa ESC'yi reverse et.

## Raspberry

```bash
ssh admin@rpi.local
cd /home/admin/isas/software
source .venv/bin/activate
source tools/pool_aliases.sh
pool-help
```

Salt okunur kontrol:

```bash
python tools/pixhawk_readonly_check.py \
  --connection /dev/serial/by-id/usb-ArduPilot_Pixhawk1_280033001951333530393639-if00
```

`RESULT: PASS` ve `Armed: False` şart.

## Tek motor (mantıksal numara)

| Komut | Fiziksel |
|---|---|
| `pool-motor 1 …` | M1 |
| `pool-motor 2 …` | M2 |
| `pool-motor 3 …` | M5 |
| `pool-motor 4 …` | **M3 taşınmış** |
| `pool-motor 5/6` | **Kullanma** (kilitli) |

Örnek:

```bash
pool-motor 4 1525 2 10
```

## Tam güç ileri — süreyi sen seç

Biçim:

```text
pool-forward -1000 SURE [GERİ_SAYIM]
```

- `-1000` = bu araçta tam fiziksel ileri
- `SURE` = 1…60 saniye
- `GERİ_SAYIM` isteğe bağlı (varsayılan 15)

Örnekler:

```bash
pool-forward -1000 5 10
pool-forward -1000 20 10
pool-forward -1000 60 15
```

Alias olmadan (SURE yerine saniye yaz):

```bash
python tools/pool_test_service.py start \
  --test straight --forward -1000 --duration SURE \
  --straight-yaw-trim 0 --countdown 10 \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-high-output HIGH_OUTPUT_RESTRAINED \
  --confirm-long-forward LONG_FULL_OUTPUT_RESTRAINED
```

Önerilen sıra: önce düşük güç, sonra tam güç.

```bash
pool-forward -300 3 10
pool-forward -1000 5 10
```

## Durum / stop / audit

```bash
pool-status
pool-stop
pool-audit --lines 8 --full
```

Wi-Fi koparsa test Raspberry'de süresince devam eder. Acil durumda fiziksel
güç kes.

## Kilitli komutlar

`pool-vertical`, `pool-combined`, `pool-turn`, `pool-mission` → şu an kilitli.
Dikey ESC'ler değişmeden / görev yeniden açılmadan kullanma.

## Arşiv notu

Eski dikey + tam görev kalibrasyon sırası (vertical/turn/circle/mission)
donanım onarılana kadar geçerli değildir. Eski eşleme arşivi:

| OUT | Eski fiziksel |
|---:|---|
| 4 | M6 sağ arka yatay |
| 5 | M3 sol dikey |
| 6 | M4 sağ dikey |
