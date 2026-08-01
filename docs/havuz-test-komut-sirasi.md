# İSAS Havuz Testi — Kesin Sıra ve Komutlar

Bu rehber 25 m × 10 m × 2,2 m havuz, Pixhawk 2.4.8/B-Cube,
ArduSub 4.7, `FRAME_CONFIG=1` Vectored, Raspberry Pi ve 1500 µs nötrlü
çift yönlü ESC düzeni içindir.

## 0. Komutların anlamı

| Parametre | Anlamı | PWM mi? |
|---|---|---|
| `--motor-pwm 1525` | Tek motor testinde doğrudan ESC PWM değeri | Evet |
| `--forward 100` | ArduSub Vectored miksere verilen ileri komutu | Hayır |
| `--vertical 550` | Dikey eksen komutu; `500` nötrdür | Hayır |
| `--turn-yaw 80` | Sağa/sola dönüş şiddeti | Hayır |
| `--turn-seconds 1` | Dönüş komutunun uygulanacağı süre | Hayır |
| `--straight-yaw-trim -5` | Düz giderken sabit küçük dönüş düzeltmesi | Hayır |
| `--circle-forward 100` | Çemberde ileri komutu | Hayır |
| `--circle-yaw 80` | Çemberde dönüş komutu | Hayır |
| `--circle-seconds 8` | Çember komutunun uygulanacağı süre | Hayır |
| `--yaw-sign 1/-1` | Tüm yaw komutlarının fiziksel yönünü seçer | Hayır |

Görev hareketleri `MANUAL` açık çevrim mixer ile çalışır. Kod pusula yaw açısını
okuyarak başlık tutmaz; dönüş açısı, düz sapma ve çember kapanması havuz
kenarından gözlenerek ayarlanır.

`--degrees 30` fiziksel dönüşü durduran değer değildir. Yalnızca beklenen açı
etiketidir. Dönüşü `--turn-seconds` bitirir.

## 1. MAIN OUT ve fiziksel motor bağlantısı

Mevcut Pixhawk parametreleri sıralıdır:

```text
SERVO1_FUNCTION=33  Motor1
SERVO2_FUNCTION=34  Motor2
SERVO3_FUNCTION=35  Motor3
SERVO4_FUNCTION=36  Motor4
SERVO5_FUNCTION=37  Motor5
SERVO6_FUNCTION=38  Motor6
```

ArduSub Vectored düzende mantıksal Motor1–Motor4 yatay, Motor5–Motor6 dikeydir.
Takımın fiziksel etiketlerinde ise M3–M4 dikeydir. Bu nedenle bağlantı şu
eşleştirmeyle yapılmalıdır:

| MAIN OUT | ArduSub mantıksal motor | Bağlanacak fiziksel motor | Konum |
|---|---:|---:|---|
| MAIN OUT 1 | Motor1 | Fiziksel M1 | Sol ön, 45° yatay |
| MAIN OUT 2 | Motor2 | Fiziksel M2 | Sağ ön, 45° yatay |
| MAIN OUT 3 | Motor3 | Fiziksel M5 | Sol arka, 45° yatay |
| MAIN OUT 4 | Motor4 | Fiziksel M6 | Sağ arka, 45° yatay |
| MAIN OUT 5 | Motor5 | Fiziksel M3 | Sol dikey |
| MAIN OUT 6 | Motor6 | Fiziksel M4 | Sağ dikey |

### Acil forward-only yeniden kablolama (2026-08-02)

Fiziksel M4 ve M6 ESC'leri arızalandı. Çalışan fiziksel M3, eski M6 yuvasına
(MAIN OUT 4 / mantıksal Motor4) taşındı. Dikey itki ve tam görev şimdilik iptal.

| MAIN OUT | ArduSub mantıksal motor | Şu anki fiziksel | Konum |
|---|---:|---:|---|
| MAIN OUT 1 | Motor1 | M1 | Sol ön, 45° yatay |
| MAIN OUT 2 | Motor2 | M2 | Sağ ön, 45° yatay |
| MAIN OUT 3 | Motor3 | M5 | Sol arka, 45° yatay |
| MAIN OUT 4 | Motor4 | **M3 (taşındı)** | Sağ arka, 45° yatay |
| MAIN OUT 5 | Motor5 | boş / kullanılmıyor | eski dikey |
| MAIN OUT 6 | Motor6 | yanmış M4 / kullanılmıyor | eski dikey |

Bu geçici düzende yalnız `pool-motor 1..4` ve `pool-forward` kullanılır.
`pool-vertical`, `pool-combined` ve `pool-mission` kilitlidir.

Bu tabloyla uyuşmayan kablo varsa birleşik hareket testi yapılmaz.

Tek motor komutundaki `--motor-number`, fiziksel etiketi değil ArduSub mantıksal
motor numarasını belirtir. Forward-only yeniden kabloda taşınmış M3 için
`--motor-number 4` kullanılır.

Kaydedilmiş ESC düzeni aşağıdadır; nihai doğrulama su içindeki itiş yönüdür:

| Fiziksel motor | Kaydedilmiş ESC ayarı | 1500 üstü, motora karşıdan bakış |
|---:|---|---|
| M1 | Bidirectional Reversed / CCW | Sola dönüş |
| M2 | Bidirectional Reversed / CCW | Sola dönüş |
| M3 | Bidirectional Normal / CW | Sağa dönüş |
| M4 | Bidirectional Reversed / CCW | Sola dönüş |
| M5 | Bidirectional Normal / CW | Sağa dönüş |
| M6 | Bidirectional Normal / CW | Sağa dönüş |

## 2. Her havuz gününün başlangıcı

Araç suya girmeden önce:

- Gövde, kablo geçişleri ve kapaklar sızdırmaz olmalı.
- Pervanelerde çatlak, gevşeklik ve yabancı madde olmamalı.
- Tüm pervane alanları boş olmalı.
- Fiziksel ana güç kesme erişilebilir olmalı.
- İlk test serbest denizde değil kontrollü havuzda yapılmalı.
- Raspberry, Pixhawk ve ESC sinyal kabloları yukarıdaki tabloya göre bağlanmalı.
- Test için yalnız gereken ESC/motor enerjilendirilmeli.

Raspberry bağlantısı:

```bash
ssh admin@rpi.local
cd /home/admin/isas/software
source .venv/bin/activate
```

Pixhawk salt-okunur kontrolü:

```bash
python tools/pixhawk_readonly_check.py \
  --connection /dev/serial/by-id/usb-ArduPilot_Pixhawk1_280033001951333530393639-if00
```

Devam şartları:

```text
Vehicle type: 12 (SUBMARINE)
Armed: False
Tüm parametreler PASS
RESULT: PASS
```

Basınç sensörü olmadığı için barometrenin `CHECK` görünmesi beklenir. Bu araç
otomatik 1 m derinlik ölçemez veya derinlik tutamaz.

## 3. Çıkışsız prova

Bu komut ARM etmez ve motor çıkışı vermez:

```bash
python tools/video_mission_runner.py
```

Beklenen son satır:

```text
RESULT: PLAN_VALID, NO CONNECTION, NO ARM, NO MOTOR OUTPUT
```

Detached servis kontrolü gerekirse:

```bash
python tools/pool_test_service.py start \
  --test straight --duration 2 --forward 100 --dry-hold 5
python tools/pool_test_service.py status
```

## 4. M1–M6 tek motor testleri

Motorlar otomatik arka arkaya çalıştırılmaz. Her motor için araç ve ekip yeniden
kontrol edilir, ardından yalnız bir komut başlatılır.

İlk turda `1525 µs`, `1 saniye` kullanılır. Örnek mantıksal Motor1:

```bash
python tools/pool_test_service.py start \
  --test motor --motor-number 1 --motor-pwm 1525 \
  --duration 1 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

Her testten sonra:

```bash
python tools/pool_test_service.py status
```

Test sırası ve gözlenecek fiziksel motor:

| Test sırası | Komuttaki değer | Hareket etmesi gereken fiziksel motor |
|---:|---:|---:|
| 1 | `--motor-number 1` | M1 |
| 2 | `--motor-number 2` | M2 |
| 3 | `--motor-number 3` | M5 |
| 4 | `--motor-number 4` | M6 |
| 5 | `--motor-number 5` | M3 |
| 6 | `--motor-number 6` | M4 |

Her testte şunlar kaydedilir:

- Yalnız beklenen motor mu çalıştı?
- 1525'te araç hangi yöne itildi?
- Titreşim, sürtme veya anormal ses var mı?
- Kablo veya ESC ısındı mı?
- Test sonunda motor durdu mu?

Ters yönü doğrulamak gerekirse aynı motor `1475 µs` ile en fazla 1 saniye
denenir:

```bash
python tools/pool_test_service.py start \
  --test motor --motor-number 1 --motor-pwm 1475 \
  --duration 1 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

İlk 1 saniyelik testler temiz geçmeden `--duration 3` kullanılmaz.

Gerçek çıkış güvenliği açıldıktan sonra yazılım, araç hâlâ DISARMED durumdayken
ESC'lerin nötr sinyali tanıması için 5 saniye bekler. MAIN OUT 1–6 telemetrisi
`1500 ±10 µs` aralığında değilse ARM ve test otomatik reddedilir. Doğrudan motor
testleri `MANUAL` modda çalışır; ARM sonrasında ikinci bir nötr kontrolü geçmeden
seçilen motora PWM uygulanmaz.

### Kalıcı Pixhawk ARM/DISARM ve telemetri kaydı

Bütün gerçek test oturumları aynı dosyaya eklenir:

```text
/home/admin/isas/software/logs/pool_tests/pixhawk-audit.jsonl
```

Bağlantı, output-safety açma/kapatma, ARM/DISARM isteği ve onayı, test
başlangıç/bitişi ve hata olayları kaydedilir. Bu olaylarda Pixhawk bağlantısında
o anda ulaşılabilen bütün MAVLink mesaj türlerinin en güncel değerleri de aynı
kayda yazılır. Her satır hemen diske kalıcı olarak aktarılır.

Son 20 olayın kısa özeti:

```bash
python tools/pool_test_service.py audit
```

Son 5 olayın bütün ham telemetri alanları:

```bash
python tools/pool_test_service.py audit --lines 5 --full
```

### Altı motoru aynı anda doğrudan PWM ile deneme

Bu test yalnızca altı tek-motor testi başarıyla tamamlandıktan sonra yapılır.
Araç tamamen su içinde ve her yöndeki hareketi fiziksel olarak sınırlandırılmış
olmalıdır. Pervanelerin çevresi boş, acil güç kesme görevlisi hazır olmalıdır.

```bash
python tools/pool_test_service.py start \
  --test motor-all --motor-pwm 1525 \
  --duration 3 --countdown 10 \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-all-motors ALL_MOTORS_RESTRAINED
```

Bu komut, MAIN OUT 1–6 üzerindeki mantıksal M1–M6 motorlarına aynı anda
`1525 µs` uygular. Bu bir `forward`/ileri komutu değildir ve vectored motor
karışımı yapmaz. Süre sonunda altı çıkışa `1500 µs` nötr gönderilir; ardından
araç DISARM edilir ve donanım çıkış güvenliği kilitlenir.

İki ek güvenlik sınırı vardır: süre en fazla 3 saniyedir ve
`ALL_MOTORS_RESTRAINED` onayı olmadan gerçek çıkış başlatılmaz.

## 5. Dikey motor testi

Fiziksel M3 ve M4 doğru çalıştıktan sonra düşük dikey komut denenir:

```bash
python tools/pool_test_service.py start \
  --test vertical --duration 1 --vertical 550 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

`550`, 1 m derinlik hedefi değildir. Yalnızca 500 nötrün üzerindeki dikey itki
komutudur. Araç yükseliyor mu, dalıyor mu ve sağa/sola yatıyor mu kaydedilir.

`550` hareket eşiğini aşmazsa araç tamamen su içinde ve sabitlenmişken güç
kademeli artırılır. Dikey komut MAVLink'in tam `0-1000` aralığını ve en fazla
60 saniyeyi destekler. `500` nötrdür; `450-550` dışı ek onay ister. Beş saniyeyi
aşan dikey test ayrıca `LONG_FULL_OUTPUT_RESTRAINED` onayı ister. Tam aralık
açık olsa da ilk güçlü deneme 1 saniye yapılır; temiz geçtikten sonra süre
kademeli artırılır:

```bash
python tools/pool_test_service.py start \
  --test vertical --duration 1 --vertical 600 --countdown 10 \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-high-output HIGH_OUTPUT_RESTRAINED
```

`0` ve `1000` uç komutlardır. Yalnızca araç tamamen su içindeyken, sabitlenmişken
ve acil güç kesme hazırken kullanılmalıdır. Yön ters çıkarsa otomatik göreve
geçilmez.

Yirmi saniyelik uç komut ancak kısa su testleri temiz geçtikten sonra kullanılır:

```bash
python tools/pool_test_service.py start \
  --test vertical --duration 20 --vertical 1000 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-high-output HIGH_OUTPUT_RESTRAINED \
  --confirm-long-vertical LONG_FULL_OUTPUT_RESTRAINED
```

## 6. Düz gidiş kalibrasyonu

Her aşama başarılı olmadan sonraki süreye geçilmez.

### 6.1 İlk 2 saniye

```bash
python tools/pool_test_service.py start \
  --test straight --duration 2 --forward 100 \
  --straight-yaw-trim 0 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

### 6.2 Beş saniye

```bash
python tools/pool_test_service.py start \
  --test straight --duration 5 --forward 100 \
  --straight-yaw-trim 0 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

### 6.3 Sapma düzeltmesi

Araç sabit biçimde sağa veya sola sapıyorsa önce küçük trim denenir:

```bash
python tools/pool_test_service.py start \
  --test straight --duration 5 --forward 100 \
  --straight-yaw-trim -5 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

Sapma artarsa işaret ters çevrilir: `-5` yerine `5`. Sonra gerekirse büyüklük
5'er adımla değiştirilir. Pusula geri beslemesi kullanılmaz.

### 6.4 Yirmi saniye

İki ve beş saniyelik testler temiz geçince:

```bash
python tools/pool_test_service.py start \
  --test straight --duration 20 --forward 100 \
  --straight-yaw-trim KALIBRE_TRIM --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

`KALIBRE_TRIM` yerine ölçülen değer yazılır. Yirmi saniyede gidilen metre,
yanal sapma ve bitiş konumu kaydedilir. Araç havuz sınırına yaklaşacaksa test
başlatılmaz veya daha düşük `--forward` kullanılır.

`--forward` tam `-1000…1000` aralığını destekler. `|forward| > 400` yüksek çıkış
onayı ister; yüksek güçte 5 saniyeyi aşan test ayrıca uzun çıkış onayı ister.
Kısa su testleri temiz geçtikten sonra tam ileri 20 saniye komutu şöyledir:

```bash
python tools/pool_test_service.py start \
  --test straight --duration 20 --forward 1000 \
  --straight-yaw-trim 0 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-high-output HIGH_OUTPUT_RESTRAINED \
  --confirm-long-forward LONG_FULL_OUTPUT_RESTRAINED
```

### 6.5 İleri ve aşağı eşzamanlı

Bu araçta fiziksel ileri yön `forward=-1000`, test edilen aşağı yön ise
`vertical=1000` olarak belirlenmiştir. Dört yatay ve iki dikey motoru ArduSub
mikseri üzerinden 20 saniye birlikte çalıştırmak için:

```bash
python tools/pool_test_service.py start \
  --test combined --duration 20 \
  --forward -1000 --vertical 1000 \
  --straight-yaw-trim 0 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-all-motors ALL_MOTORS_RESTRAINED \
  --confirm-high-output HIGH_OUTPUT_RESTRAINED \
  --confirm-long-forward LONG_FULL_OUTPUT_RESTRAINED \
  --confirm-long-vertical LONG_FULL_OUTPUT_RESTRAINED
```

Bu komut doğrudan altı çıkışa aynı PWM'i yazmaz; ileri ve dikey eksenleri
ArduSub vektör mikserine aynı anda verir.

### 6.6 Kısa havuz komutları

Alias kurulumu bir kez yapılır:

```bash
cd /home/admin/isas/software
.venv/bin/python tools/install_pool_aliases.py
source ~/.bashrc
pool-help
```

Sonrasında güç ve süre doğrudan verilebilir:

```bash
pool-forward -1000 60
pool-vertical 1000 60
pool-combined -1000 1000 60
pool-turn 1000 60
pool-status
pool-stop
pool-audit --lines 5 --full
```

İsteğe bağlı son sayı geri sayımdır; örneğin `pool-forward -700 15 10`, 10
saniye geri sayımdan sonra `-700` ileri komutunu 15 saniye uygular. İzin verilen
aralıklar ileri ve dönüş için `-1000…1000` (`0` hariç), dikey için `0…1000`,
hareket süresi için `1…60`, dönüş süresi için `0.2…60` saniyedir.

## 7. Sağ dönüş kalibrasyonu

`turn-yaw` tam `-1000…1000` aralığını, `turn-seconds` ise `0.2…60` saniyeyi
destekler. Kısa alias biçimi `pool-turn YAW SÜRE [GERİ_SAYIM]` şeklindedir.
Örneğin `pool-turn -650 2.5 10`, 10 saniye geri sayımdan sonra `-650` yaw
komutunu 2.5 saniye uygular. İşaret gerçek sağ/sol yönü havuzda gözlenerek
belirlenir.

İlk test düşük güç ve kısa süreyle yapılır:

```bash
python tools/pool_test_service.py start \
  --test turn-right --degrees 30 \
  --turn-yaw 80 --turn-seconds 1 --yaw-sign 1 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

Araç sola dönüyorsa `--yaw-sign -1` denenir. Doğru işaret bulunduktan sonra
dışarıdan gerçekleşen açı ölçülür.

Örnek: `1 saniye` ve `yaw=80` ile araç `40°` döndüyse 90° için ilk tahmin:

```text
90 / 40 × 1 = 2,25 saniye
```

İlk 90° denemesi tahminden biraz kısa tutulur:

```bash
python tools/pool_test_service.py start \
  --test turn-right --degrees 90 \
  --turn-yaw 80 --turn-seconds 2 --yaw-sign KALIBRE_YAW_SIGN \
  --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR
```

Akü gerilimi ve su direnci dönüş süresini değiştirebilir. Son değer birden fazla
denemeyle doğrulanır.

## 8. Yaklaşık 2 m çember kalibrasyonu

İlk kısa deneme:

```bash
python tools/pool_test_service.py start \
  --test circle --circle-forward 100 --circle-yaw 80 \
  --circle-seconds 8 --yaw-sign KALIBRE_YAW_SIGN --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

- Daha fazla yaw veya daha az ileri komut genellikle çemberi küçültür.
- Daha fazla ileri veya daha az yaw komutu genellikle çemberi büyütür.
- `--circle-seconds`, çemberin çapını değil ne zaman biteceğini belirler.
- Araç 360° tamamladığında dışarıdan geçen süre kaydedilir.
- Ölçülen süre sonraki testte `--circle-seconds` olarak kullanılır.

Yaklaşık 2 m çap ve başlangıç noktasına güvenli dönüş birkaç kez
tekrarlanabilir biçimde doğrulanmalıdır.

## 9. Derinlik konusu

Mevcut tam görev planında otomatik dalış adımı yoktur. Basınç sensörü bulunmadığı
için araç “1 m derine indim” bilgisini ölçemez. Video çekiminde araç istenen
başlangıç derinliğine kontrollü biçimde yerleştirilir veya ayrı dikey testte
kalibre edilen süreyle operatör gözetiminde indirilir. Kalibre edilmemiş dikey
hareket tam göreve eklenmez.

## 10. Tam görev dry-run

Kalibre edilen değerler yazılarak önce çıkışsız prova yapılır:

```bash
python tools/video_mission_runner.py \
  --forward KALIBRE_FORWARD \
  --straight-yaw-trim KALIBRE_TRIM \
  --turn-yaw KALIBRE_TURN_YAW \
  --turn-seconds KALIBRE_90_SANIYE \
  --circle-forward KALIBRE_CIRCLE_FORWARD \
  --circle-yaw KALIBRE_CIRCLE_YAW \
  --circle-seconds KALIBRE_CIRCLE_SANIYE \
  --yaw-sign KALIBRE_YAW_SIGN
```

Mevcut tam görev sırası:

1. 5 saniye nötr bekleme.
2. 20 saniye düz gidiş.
3. Kalibre edilmiş süreyle yaklaşık 90° sağ dönüş.
4. 20 saniye düz gidiş.
5. Kalibre edilmiş süreyle yaklaşık 2 m çaplı sağ çember.
6. Kalibre edilmiş süreyle yaklaşık 90° sağ dönüş.
7. 20 saniye düz gidiş.
8. Kalibre edilmiş süreyle yaklaşık 90° sağ dönüş.
9. 20 saniye düz gidiş.
10. Nötr ve DISARM.

## 11. Tam görev — yalnız tüm kalibrasyonlar geçince

```bash
python tools/pool_test_service.py start \
  --test mission \
  --forward KALIBRE_FORWARD \
  --straight-yaw-trim KALIBRE_TRIM \
  --turn-yaw KALIBRE_TURN_YAW \
  --turn-seconds KALIBRE_90_SANIYE \
  --circle-forward KALIBRE_CIRCLE_FORWARD \
  --circle-yaw KALIBRE_CIRCLE_YAW \
  --circle-seconds KALIBRE_CIRCLE_SANIYE \
  --yaw-sign KALIBRE_YAW_SIGN \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-full-mission FULL_MISSION_TUNED
```

Bu komut ilk havuz testi değildir. M1–M6, dikey, düz, dönüş ve çember testleri
ayrı ayrı geçmeden çalıştırılmaz.

## 12. Durum ve durdurma

Çalışan veya son testi görmek:

```bash
python tools/pool_test_service.py status
```

Wi-Fi/SSH bağlantısı varken güvenli durdurma:

```bash
python tools/pool_test_service.py stop
```

Runner gerçek testte şu sırayı otomatik uygular:

1. DISARMED geri sayım.
2. Pixhawk hardware output safety kilidini ACK ile açma.
3. ARM.
4. Sonlu süreli komut.
5. Nötr.
6. DISARM.
7. Hardware output safety kilidini yeniden uygulama.

Su altında Wi-Fi kesilirse Raspberry seçilen sonlu testi yerelde tamamlar. Bu
sırada yeni komut ve uzaktan `stop` garanti edilmez. Fiziksel ana güç kesme tek
kesin acil durdurmadır.

## 13. Kalibrasyon kayıt tablosu

| Test | Komut değerleri | Ölçülen sonuç | Karar |
|---|---|---|---|
| Mantıksal M1 → fiziksel M1 | `1525`, 1 s |  |  |
| Mantıksal M2 → fiziksel M2 | `1525`, 1 s |  |  |
| Mantıksal M3 → fiziksel M5 | `1525`, 1 s |  |  |
| Mantıksal M4 → fiziksel M6 | `1525`, 1 s |  |  |
| Mantıksal M5 → fiziksel M3 | `1525`, 1 s |  |  |
| Mantıksal M6 → fiziksel M4 | `1525`, 1 s |  |  |
| Dikey | `vertical=550`, 1 s |  |  |
| Düz kısa | `forward=100`, 2 s |  |  |
| Düz orta | `forward=100`, 5 s |  |  |
| Düz uzun | `forward=...`, 20 s |  |  |
| Sağ dönüş | `yaw=...`, `seconds=...` |  |  |
| Çember | `forward=...`, `yaw=...`, `seconds=...` |  |  |

Tam görev yalnız tablodaki tüm satırlar doğrulanıp kullanılan nihai değerler
kaydedildikten sonra açılır.

## 14. Birlikte kalibrasyon çalışma biçimi

Her aşamada aynı döngüyü kullanacağız:

1. Aşağıdaki aşama check-up'ını tamamla.
2. Belirtilen **başlatma mesajını** bu konuşmaya gönder.
3. Ben aynı ağdaki Raspberry'ye bağlanıp yalnız o sonlu testi başlatayım.
4. Testi havuz kenarından ve mümkünse üstten videoyla gözle.
5. İlgili **sonuç raporunu** kopyalayıp doldurarak bana gönder.
6. Ben ölçüme göre bir sonraki komut değerlerini hesaplayayım.
7. Ben açıkça “bu aşama geçti” demeden sonraki aşamaya geçme.

Raspberry'ye uzaktan bağlanamazsam çalıştırılacak terminal komutunu sana
vereceğim. Araç su altına girdikten sonra Wi-Fi bağlantısının kesilmesi normaldir;
başlatılmış sonlu test Raspberry üzerinde devam eder.

### 14.1 Her gerçek testten önce ortak check-up

Her başlatma mesajından önce tüm kutular işaretlenmelidir:

- [ ] Araç tamamen su içinde.
- [ ] Pervane alanları boş.
- [ ] Kimsenin eli veya kablosu pervanelere yaklaşmıyor.
- [ ] Fiziksel ana güç kesme erişilebilir.
- [ ] Araç havuz duvarından ve tabandan güvenli mesafede.
- [ ] Raspberry ve Pixhawk enerjili.
- [ ] ESC/motor bağlantıları test tablosuna uygun.
- [ ] Önceki test tamamen bitmiş ve motorlar durmuş.
- [ ] Araç yeniden başlangıç çizgisine/yönüne yerleştirilmiş.
- [ ] Testi gözleyecek kişi ve video kaydı hazır.

Ortak başlatma mesajı biçimi:

```text
TEST HAZIR: [test adı]
Araç tamamen suda: EVET
Pervane alanı boş: EVET
Fiziksel güç kesme hazır: EVET
Araç duvarlardan güvenli uzakta: EVET
Başlatabilirsin.
```

Bu beş satır eksikse gerçek motor çıkışı başlatılmaz.

## 15. Motor check-up ve bana gönderilecek rapor

Motorlar şu sırayla test edilir:

```text
Mantıksal 1 → fiziksel M1
Mantıksal 2 → fiziksel M2
Mantıksal 3 → fiziksel M5
Mantıksal 4 → fiziksel M6
Mantıksal 5 → fiziksel M3 (dikey)
Mantıksal 6 → fiziksel M4 (dikey)
```

Her motor öncesi ek check-up:

- [ ] Test edilecek fiziksel motoru elle gösterip etiketi doğruladım.
- [ ] Hangi MAIN OUT'a bağlı olduğunu tabloyla doğruladım.
- [ ] İlk test süresi 1 saniye.
- [ ] İlk test PWM değeri 1525.
- [ ] Diğer motorların da su içinde olduğundan emin oldum.

Örnek başlatma mesajı:

```text
TEST HAZIR: Mantıksal Motor1 / fiziksel M1
Araç tamamen suda: EVET
Pervane alanı boş: EVET
Fiziksel güç kesme hazır: EVET
Araç duvarlardan güvenli uzakta: EVET
1525 PWM, 1 saniye başlatabilirsin.
```

Testten sonra bunu doldurup gönder:

```text
MOTOR TEST RAPORU
Komuttaki mantıksal motor numarası:
Hareket etmesi gereken fiziksel motor:
Gerçekte hareket eden fiziksel motor:
PWM / süre:
Yalnız beklenen motor çalıştı mı: EVET / HAYIR
Motora karşıdan bakınca dönüş: SAĞ / SOL / BELİRSİZ
Aracı ittiği yön: İLERİ / GERİ / YUKARI / AŞAĞI / YAN / BELİRSİZ
Titreşim veya anormal ses: YOK / VAR — açıklama:
Kablo veya ESC ısınması: YOK / VAR — açıklama:
Komut sonunda tamamen durdu mu: EVET / HAYIR
Video var mı: EVET / HAYIR
Ek gözlem:
```

Şu durumlardan biri varsa sonraki motora geçilmez:

- Beklenmeyen başka motorun çalışması.
- Motorun komut sonunda durmaması.
- Anormal ses, titreşim, sürtme veya ısınma.
- Kablo/MAIN OUT eşleşmesinin tabloyla uyuşmaması.
- Beklenen itiş yönünün ters olması.

## 16. Dikey hareket check-up ve rapor

Bu aşamaya yalnız altı motor testi geçtiğinde gelinir.

Ek check-up:

- [ ] Fiziksel M3 ve M4 dikey motor testleri geçti.
- [ ] Araç tabandan en az güvenli deneme mesafesinde.
- [ ] Araç yüzeye çarpmayacak derinlikte.
- [ ] İlk komut `vertical=550`, süre 1 saniye.

Başlatma mesajı:

```text
TEST HAZIR: Dikey 550 / 1 saniye
Araç tamamen suda: EVET
Pervane alanı boş: EVET
Fiziksel güç kesme hazır: EVET
Araç taban ve yüzeyden güvenli uzakta: EVET
Başlatabilirsin.
```

Sonuç raporu:

```text
DİKEY TEST RAPORU
Vertical komutu / süre:
Araç: YÜKSELDİ / DALDI / HAREKET ETMEDİ
Yaklaşık dikey hareket miktarı:
Sağa veya sola yattı mı:
Öne veya arkaya yattı mı:
İki dikey motor dengeli göründü mü: EVET / HAYIR / BELİRSİZ
Komut sonunda durdu mu: EVET / HAYIR
Video var mı: EVET / HAYIR
Ek gözlem:
```

Ben bu rapora göre yönün doğru olup olmadığını söyleyeceğim. Gerekirse yalnız
yön teşhisi için `vertical=450` testi planlarız.

## 17. Düz gidiş check-up ve kalibrasyon raporu

Düz test sırası `2 saniye → 5 saniye → trimli 5 saniye → 20 saniye` şeklindedir.

Ek check-up:

- [ ] Yatay fiziksel M1, M2, M5 ve M6 motor testleri geçti.
- [ ] Araç burnu havuz çizgisine paralel yerleştirildi.
- [ ] Başlangıç noktası işaretlendi.
- [ ] Havuz kenarında metre veya referans çizgileri hazır.
- [ ] İlk test `forward=100`, `trim=0`, süre 2 saniye.

İlk başlatma mesajı:

```text
TEST HAZIR: Düz 2 saniye
Araç tamamen suda: EVET
Pervane alanı boş: EVET
Fiziksel güç kesme hazır: EVET
İleri yönde yeterli boş mesafe: EVET
forward=100, trim=0 başlatabilirsin.
```

Her düz testten sonra gönderilecek rapor:

```text
DÜZ TEST RAPORU
Forward / trim / süre:
Yaklaşık gidilen mesafe (metre):
Başlangıç yönüne göre sapma: SAĞ / SOL / YOK
Yaklaşık yanal sapma (cm veya metre):
Araç kendi etrafında döndü mü; yaklaşık kaç derece:
Yükselme veya dalma oldu mu:
Test sonunda duvara kalan yaklaşık mesafe:
Komut sonunda durdu mu: EVET / HAYIR
Video var mı: EVET / HAYIR
Ek gözlem:
```

Ben rapora göre:

- sapma yoksa 5 saniyelik teste,
- sağa/sola sapma varsa ilk `straight-yaw-trim` değerine,
- hız fazla veya azsa yeni `forward` değerine

karar vereceğim. Trim önce `±5` adımla denenir. Trim yönünü tahmin ederek kendi
başına değiştirme; gözlemi gönder, sonraki değeri birlikte seçelim.

## 18. Yaw-sign ve 90° dönüş kalibrasyonu

Bu aşamada önce yalnız dönüş yönünü, sonra dönüş süresini bulacağız.

Ek check-up:

- [ ] Düz 5 saniyelik test kontrol altında geçti.
- [ ] Araç havuz duvarlarından dönüş yapabilecek kadar uzakta.
- [ ] Başlangıç burun yönü zeminde/kenarda işaretlendi.
- [ ] Üstten video veya açı ölçümü hazır.
- [ ] İlk test `turn-yaw=80`, `turn-seconds=1`, `yaw-sign=1`.

İlk başlatma mesajı:

```text
TEST HAZIR: Yaw yön testi
Araç tamamen suda: EVET
Pervane alanı boş: EVET
Fiziksel güç kesme hazır: EVET
Dönüş için çevresi boş: EVET
turn-yaw=80, turn-seconds=1, yaw-sign=1 başlatabilirsin.
```

Sonuç raporu:

```text
YAW / DÖNÜŞ TEST RAPORU
Yaw-sign:
Turn-yaw:
Turn-seconds:
Araç fiziksel olarak: SAĞA / SOLA döndü
Yaklaşık gerçekleşen açı (derece):
Araç dönüş sırasında ileri/geri kaydı mı:
Yükselme veya dalma oldu mu:
Komut sonunda dönmeye devam etti mi:
Video var mı: EVET / HAYIR
Ek gözlem:
```

Karar:

- Sağa döndüyse `KALIBRE_YAW_SIGN=1` adayıdır.
- Sola döndüyse sonraki test `yaw-sign=-1` olur.
- Doğru yön bulunduktan sonra 1 saniyede ölçülen açıyla 90° süre tahmini yapılır.
- İlk 90° denemesi hesaplanan süreden biraz kısa tutulur.
- Aynı değerin en az iki tekrarda yaklaşık aynı sonucu vermesi gerekir.

Ölçülen açı çok belirsizse “yaklaşık 30°” yazmak yerine videoyu ve başlangıç/
bitiş yönünü gönder; yanlış hassasiyetle hesap yapmayalım.

## 19. Çember check-up ve kalibrasyon raporu

Ek check-up:

- [ ] Doğru `KALIBRE_YAW_SIGN` bulundu.
- [ ] Yaklaşık 90° dönüş süresi en az iki kez doğrulandı.
- [ ] Araç yaklaşık 2 m çaplı çember için duvarlardan yeterince uzakta.
- [ ] Başlangıç noktası ve burun yönü işaretlendi.
- [ ] Üstten veya yüksek açıdan video hazır.

İlk başlatma mesajı:

```text
TEST HAZIR: Çember ilk prova
Araç tamamen suda: EVET
Pervane alanı boş: EVET
Fiziksel güç kesme hazır: EVET
Çember için çevresi boş: EVET
circle-forward=100, circle-yaw=80, circle-seconds=8,
yaw-sign=[bulduğumuz değer] başlatabilirsin.
```

Sonuç raporu:

```text
ÇEMBER TEST RAPORU
Circle-forward:
Circle-yaw:
Circle-seconds:
Yaw-sign:
Dönüş yönü: SAĞ / SOL
Tamamlanan yaklaşık açı: derece veya tur oranı
Ölçülen yaklaşık çap (metre):
Başlangıç noktasına göre bitiş uzaklığı (metre):
Çember kapandı mı: ERKEN DURDU / YAKLAŞIK KAPANDI / BAŞLANGICI GEÇTİ
Derinlik belirgin değişti mi:
Duvara en yakın yaklaşık mesafe:
Komut sonunda durdu mu: EVET / HAYIR
Video var mı: EVET / HAYIR
Ek gözlem:
```

Ben rapora göre üç değerden hangisinin değişeceğini söyleyeceğim:

- Çap için `circle-forward / circle-yaw` oranı,
- 360° kapanma için `circle-seconds`,
- fiziksel sağ yön için `yaw-sign`.

Aynı anda bütün değerleri değiştirmeyeceğiz; hangi değişikliğin ne sonuç
verdiğini görebilmek için her turda mümkünse tek değişken değiştirilir.

## 20. Tam görev öncesi son check-up

Tam görev komutu ancak bütün kutular işaretliyse hazırlanır:

- [ ] Altı mantıksal motor doğru fiziksel motoru çalıştırdı.
- [ ] Tüm motorların ileri/geri itiş yönü doğrulandı.
- [ ] Dikey 550 yönü ve denge davranışı doğrulandı.
- [ ] `KALIBRE_FORWARD` bulundu.
- [ ] `KALIBRE_TRIM` bulundu.
- [ ] `KALIBRE_YAW_SIGN` bulundu.
- [ ] `KALIBRE_TURN_YAW` bulundu.
- [ ] `KALIBRE_90_SANIYE` en az iki kez doğrulandı.
- [ ] `KALIBRE_CIRCLE_FORWARD` bulundu.
- [ ] `KALIBRE_CIRCLE_YAW` bulundu.
- [ ] `KALIBRE_CIRCLE_SANIYE` en az iki kez doğrulandı.
- [ ] 20 saniyelik düz test havuz sınırları içinde güvenli tamamlandı.
- [ ] Tam görev dry-run çıktısı kontrol edildi.
- [ ] Fiziksel ana güç kesme ve kurtarma planı hazır.
- [ ] Video ekibi ve havuz alanı hazır.

Bana gönderilecek son özet:

```text
TAM GÖREV KALİBRASYON ÖZETİ
KALIBRE_FORWARD=
KALIBRE_TRIM=
KALIBRE_YAW_SIGN=
KALIBRE_TURN_YAW=
KALIBRE_90_SANIYE=
KALIBRE_CIRCLE_FORWARD=
KALIBRE_CIRCLE_YAW=
KALIBRE_CIRCLE_SANIYE=
20 saniyede gidilen mesafe=
Yaklaşık çember çapı=
Tüm ayrı testler geçti mi: EVET / HAYIR
Tam görev dry-run geçti mi: EVET / HAYIR
Ek risk veya gözlem=
```

Bu özeti birlikte kontrol ettikten sonra gerçek tam görev komutunu nihai
değerlerle oluşturacağız.
