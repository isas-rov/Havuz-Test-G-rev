# İSAS Havuz Test Görev Yazılımı

Pixhawk 2.4.8 üzerinde ArduSub 4.7, `FRAME_CONFIG=1` Vectored araç ve
Raspberry Pi için güvenlik kilitli havuz test araçlarıdır.

Bu repo şunları içerir:

- Pixhawk parametre ve sensörlerinin salt-okunur kontrolü
- M1-M6 motorlarının operatör komutuyla **tek tek** denenmesi
- MANUAL açık çevrim mixer ile pusulasız süreli hareket kalibrasyonları
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

Görev hareketleri `MANUAL` açık çevrim mixer ile çalışır. Kod pusula yaw açısını
okumaz ve bir başlığı tutmaya çalışmaz. Dönüş açısı, düz gidiş sapması ve çember kapanması havuzda dışarıdan
ölçülerek süre/komut değerleri ayarlanır. Pusula Pixhawk sağlık/arming kontrolünde
şimdilik etkin kalabilir, ancak rota kararında kullanılmaz.

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

Doğrudan motor testleri `MANUAL` modda yürütülür. Safety açıldıktan sonra ARM
öncesinde ve ARM sonrasında MAIN OUT 1–6 değerleri `1500 ±10 µs` değilse test
otomatik olarak reddedilir; böylece kontrolcünün başka motorları sürmesine izin
verilmez.

Durum ve log:

```bash
python tools/pool_test_service.py status
```

Altı tek-motor testi geçtikten sonra, araç tamamen su içinde ve fiziksel olarak
sabitlenmişken M1–M6 aynı doğrudan PWM ile en fazla 3 saniye denenebilir:

```bash
python tools/pool_test_service.py start \
  --test motor-all --motor-pwm 1525 --duration 3 --countdown 10 \
  --enable-output --confirm MOTORS_ARE_CLEAR \
  --confirm-all-motors ALL_MOTORS_RESTRAINED
```

Bu bir ileri hareket komutu değil, altı çıkışın eşzamanlı doğrudan PWM testidir.

Dikey komut `0–1000`, ileri komutu `-1000–1000` aralığını destekler; `500`
dikey nötrdür. İleri, dikey ve birleşik hareket testlerinde süre `1–60`
saniyedir. Yüksek ve uzun çıkışlar ek onay ister; doğrudan tekli ve eşzamanlı
motor PWM testleri ise en fazla 3 saniye olarak kalır.

Raspberry üzerinde ayarlanabilir kısa komutları bir kez kurmak için:

```bash
cd /home/admin/isas/software
.venv/bin/python tools/install_pool_aliases.py
source ~/.bashrc
pool-help
```

Örnekler:

```bash
pool-motor 6 1525 2 10
pool-motor 5 1525 2 10
pool-forward -300 3 10
pool-vertical 600 3 10
pool-combined -300 600 3 10
pool-turn 300 2 10
pool-mission 15
pool-status
pool-stop
```

`pool-vertical` tek mixer `z` komutudur; fiziksel M3 ve M4 aynı dikey
itkiyi alır. Mantıksal motor `5` = fiziksel M3, `6` = fiziksel M4.

`pool-mission` ileri kategori videosu sırasını çalıştırır (bekle → isteğe bağlı
açık-çevrim dalış → 4×20 s düz → 90° dönüşler → ~2 m çember → stop). Önce
havuzda `forward`, `turn-seconds`, `circle-*` ve `yaw-sign` kalibre edilmelidir.
Alias içindeki varsayılanlar yer tutucudur; kalibrasyondan sonra
`tools/pool_aliases.sh` içindeki `pool-mission()` değerlerini güncelleyin. Alias
başlangıçta `mission_calibrated="NO"` ile kilitlidir. Fiziksel M4/M6 onarılıp
düz gidiş, dalış, 90° dönüş ve yaklaşık 2 m çember ayrı ayrı doğrulandıktan sonra
son ölçülen değerleri kaydedin ve bu alanı `YES` yapın.

Bağlantı varken güvenli durdurma:

```bash
python tools/pool_test_service.py stop
```

## Tek dosyada Pixhawk ARM/DISARM ve telemetri kaydı

Gerçek testlerin bütün oturum olayları şu kalıcı JSONL dosyasına eklenir:

```text
logs/pool_tests/pixhawk-audit.jsonl
```

Her bağlantı, safety değişimi, ARM/DISARM isteği ve onayı, test başlangıcı/bitişi
ile hata kaydında o anda ulaşılabilen bütün MAVLink mesaj türlerinin son örneği
saklanır. Okunabilir son 20 olay:

```bash
python tools/pool_test_service.py audit
```

Son 5 olayın bütün ham telemetri alanları:

```bash
python tools/pool_test_service.py audit --lines 5 --full
```

Diğer havuz kalibrasyonlarının sırası ve kayıt edilecek ölçümler için
[`docs/pool-test-runbook.md`](docs/pool-test-runbook.md) dosyasına bakın.
Sahada uygulanacak kesin komut sırası için
[`docs/havuz-test-komut-sirasi.md`](docs/havuz-test-komut-sirasi.md) dosyasını
kullanın.

## Çıkış kilitleri

- Parametresiz veya `--enable-output` olmadan çalıştırma yalnız dry-run yapar.
- Gerçek test `--enable-output --confirm MOTORS_ARE_CLEAR` ister.
- Tam görev ayrıca `--confirm-full-mission FULL_MISSION_TUNED` ister.
- Tam görev geri sayımı ARM ve safety kilidi açılmadan önce tamamlanır.
- Düğmesiz Pixhawk'ta çıkış safety kilidi yalnız geri sayım ve onaydan sonra
  yazılımla açılır; test sonunda DISARM'dan sonra tekrar kilitlenir.
- Servis açılışta otomatik başlamaz ve biten/hata veren testi yeniden başlatmaz.
