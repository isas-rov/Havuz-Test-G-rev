# İSAS Havuz Test Görev Yazılımı

Pixhawk 2.4.8 üzerinde ArduSub 4.7, `FRAME_CONFIG=1` Vectored araç ve
Raspberry Pi için güvenlik kilitli havuz test araçlarıdır.

Bu repo şunları içerir:

- Pixhawk parametre ve sensörlerinin salt-okunur kontrolü
- M1-M6 motorlarının operatör komutuyla **tek tek** denenmesi
- Süreli düz, dikey, yaw ve çember kalibrasyonları
- SSH/Wi-Fi koptuğunda Raspberry üzerinde devam eden tek-seferlik test servisi
- Görev videosu parkurunun donanımsız provası ve güvenlik kilitli çalıştırıcısı

## Güvenlik sınırı

Wi-Fi su altında güvenilir değildir. Test yüzeyde başlatılır; Raspberry Pi,
bağlantı kesilse bile seçilen sonlu testi yerel olarak tamamlar. Su altındayken
yeni komut veya uzaktan durdurma garanti edilemez.

Gerçek çıkış yalnız araç tamamen su içindeyken, pervane alanı boşken, araç
kontrollü bir test düzeneğinde tutulurken ve enerji kesme erişilebilirken açılır.
Denizde serbest araçla ilk test yapılmaz.

## Raspberry Pi kurulumu

```bash
git clone https://github.com/isas-rov/Havuz-Test-G-rev.git
cd Havuz-Test-G-rev
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,vehicle]"
pytest -q
```

Telefon/havuz Wi-Fi profilini bir kez yapılandırma:

```bash
sudo bash tools/configure_pool_wifi.sh ISAS-Phone
```

## Her testten önce

```bash
source .venv/bin/activate
python tools/pixhawk_readonly_check.py \
  --connection /dev/serial/by-id/usb-ArduPilot_Pixhawk1_280033001951333530393639-if00
```

`RESULT: PASS` ve `Armed: False` görülmeden gerçek çıkış verilmez. Basınç
sensörü bulunmadığı için barometrenin `CHECK` görünmesi mevcut donanımda
beklenir; otomatik derinlik ölçümü/tutma kullanılamaz.

## Tek motor testi

Motorlar otomatik sırayla çalışmaz. Operatör hangi motorun hazır olduğunu
bildirir ve yalnız o motor için ayrı test başlatılır. Örnek M1:

```bash
python tools/pool_test_service.py start \
  --test motor --motor-number 1 --motor-pwm 1525 --duration 3 --countdown 15 \
  --enable-output --confirm MOTORS_ARE_CLEAR
```

Akış: 15 saniye DISARMED geri sayım, seçilen motor için 3 saniye düşük PWM,
1500 nötr ve DISARM. Ters yön kontrolü gerektiğinde `--motor-pwm 1475`
kullanılır. `1525/1475` doğrudan PWM'dir; yüzde komutu kullanılmaz.

Durum ve log:

```bash
python tools/pool_test_service.py status
```

Bağlantı varken güvenli durdurma:

```bash
python tools/pool_test_service.py stop
```

Diğer havuz kalibrasyonlarının sırası ve kayıt edilecek ölçümler için
[`docs/pool-test-runbook.md`](docs/pool-test-runbook.md) dosyasına bakın.

## Çıkış kilitleri

- Parametresiz veya `--enable-output` olmadan çalıştırma yalnız dry-run yapar.
- Gerçek test `--enable-output --confirm MOTORS_ARE_CLEAR` ister.
- Tam görev ayrıca `--confirm-full-mission FULL_MISSION_TUNED` ister.
- Servis açılışta otomatik başlamaz ve biten/hata veren testi yeniden başlatmaz.
