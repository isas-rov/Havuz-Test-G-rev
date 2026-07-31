# Havuz Testi Çalıştırma Sırası

Bu akış 25 m × 10 m × 2,2 m havuz ve 1500 µs nötr çift yönlü ESC'ler
için hazırlanmıştır. Araç her gerçek testte tamamen su içinde olmalı, pervane
alanı boş tutulmalı ve fiziksel ana güç kesme erişilebilir olmalıdır.

## 1. Raspberry Pi oturumu

```bash
cd /home/admin/isas/software
source .venv/bin/activate
```

SSH veya Wi-Fi kopsa bile `pool_test_service.py start` ile başlatılan test,
Raspberry Pi üzerindeki bağımsız systemd kullanıcı servisi olarak devam eder.
Servis açılışta otomatik başlamaz ve biten testi yeniden başlatmaz.

Telefon/havuz erişim noktası profili için bir kez:

```bash
sudo bash tools/configure_pool_wifi.sh ISAS-Phone
```

Bu ayar profili otomatik bağlanır yapar, yeniden bağlanmayı süresiz dener ve
Wi-Fi güç tasarrufunu kapatır. Raspberry su altındayken radyo bağlantısının
kesilmesi normaldir. Araç yüzeye çıkıp aynı ağ yeniden görüldüğünde NetworkManager
profili tekrar etkinleştirir; bu sırada IP adresi değişebilir.

## 2. Pixhawk salt-okunur kontrolü

```bash
python tools/pixhawk_readonly_check.py --connection /dev/serial/by-id/usb-ArduPilot_Pixhawk1_280033001951333530393639-if00
```

`RESULT: PASS` görülmeden motor çıkışı verilmez.

## 3. M1-M6 tek motor testleri

İlk turda her motor yalnızca 1 saniye ve nötrün 25 µs üstünde denenir. Aşağıdaki
komutta motor numarası sırayla 1, 2, 3, 4, 5 ve 6 yapılır:

```bash
python tools/pool_test_service.py start --test motor --motor-number 1 --motor-pwm 1525 --duration 1 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR
```

Her testten sonra:

```bash
python tools/pool_test_service.py status
```

Yön tersini ayrıca görmek gerekirse aynı motor yalnızca `--motor-pwm 1475` ile
denenir. `1500` nötrdür; yazılım güvenlik amacıyla motor testi olarak kabul etmez.

Motorlar otomatik sırayla çalıştırılmaz. Operatör hazır olduğunu bildirdikçe
`--motor-number` değiştirilerek her motor ayrı başlatılır. Her ayrı çalıştırma
sonunda ilgili motor nötrlenir ve araç DISARM edilir. Test süresi gerektiğinde
`--duration 3` yapılabilir.

## 4. Birleşik hareket kalibrasyonu

Testler sırayla ve her birinin sonucu doğrulandıktan sonra yapılır:

```bash
# İleri: önce 2 s, sonra 5 s, ölçüm uygunsa 20 s
python tools/pool_test_service.py start --test straight --duration 2 --forward 100 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR
python tools/pool_test_service.py start --test straight --duration 5 --forward 100 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR
python tools/pool_test_service.py start --test straight --duration 20 --forward 100 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR

# Dikey yön: önce 1 s; bu derinlik hedefi değil, açık çevrim itki testidir
python tools/pool_test_service.py start --test vertical --duration 1 --vertical 550 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR

# Yaw yönü ve pusula geri beslemesi: önce 30°, sonra 90°
python tools/pool_test_service.py start --test turn-right --degrees 30 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR
python tools/pool_test_service.py start --test turn-right --degrees 90 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR

# Yaklaşık 2 m çap hedefi için ilk çember kalibrasyonu
python tools/pool_test_service.py start --test circle --circle-forward 100 --circle-yaw 80 --countdown 15 --enable-output --confirm MOTORS_ARE_CLEAR
```

Bir test sırasında bağlantı varsa güvenli durdurma:

```bash
python tools/pool_test_service.py stop
```

Bağlantı yoksa uzaktan durdurma mümkün değildir; fiziksel ana güç kesme tek
acil durdurmadır. Raspberry Pi veya USB-MAVLink tamamen kaybolursa Pixhawk'ın
GCS failsafe ayarı motorları durdurur.

## 5. Kayıt edilecek ölçümler

- M1-M6: motor numarası, 1525'te aracın hangi yöne itildiği, titreşim/ses
- İleri test: süre, gidilen metre, sağa/sola sapma, son yaw
- Dikey test: 550 komutunda araç yükseldi mi daldı mı
- Dönüş: istenen açı, gerçekleşen yön, tamamlanma süresi
- Çember: yaklaşık çap, tamamlanma süresi, başlangıç ve bitiş konumu

Basınç sensörü olmadığı için 1 m derinlik otomatik ölçülemez veya tutulamaz.
İlk iniş süresi ve dikey komutu, havuzda dışarıdan gözlenerek kalibre edilmelidir.
