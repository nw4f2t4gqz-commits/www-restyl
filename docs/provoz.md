# Provoz a zálohování

## Součásti zálohy

Zálohujte společně databázi, Drupal soubory v `drupal_files`, soukromé soubory
a hash salt v `drupal_private`, konfiguraci prostředí a verzovaný kód včetně
`composer.lock`. Bez databáze nelze obnovit redakční úpravy; samotný adresář
`content/` je pouze počáteční snapshot veřejného webu. Zálohy mohou obsahovat
osobní údaje a tajemství: šifrujte je, omezte přístup a ukládejte kopii mimo
NAS. Nastavte dobu uchování a pravidelně zkoušejte obnovu.

## Lokální záloha

Postup se skripty `ops/backup.sh` a `ops/restore.sh` je v
[README](../README.md). Pro dobu zálohy zajistěte, že nikdo nezapisuje do webu.
Při chybě nepovažujte neúplnou zálohu za platnou. `.env` případně zálohujte
samostatně jako tajný soubor; nikdy jej neukládejte do repozitáře.

## Obnova a produkční provoz

Obnovu provádějte nejprve do samostatné prázdné databáze a prázdných úložišť,
nikdy přes živý web bez schválení a ověřené zálohy. Obnovte databázový dump,
obsah archivů do odpovídajících úložišť a stejnou verzi kódu a konfigurace.
Ověřte přihlášení, obsah, obrázky, formulář i oprávnění. Přesný postup pro NAS
závisí na konkrétní instalaci a musí být před uvedením do provozu vyzkoušen.

Produkční nasazení není součástí lokálního Compose. Před spuštěním jsou nutné
ověřené HTTPS, omezení administrace na LAN/VPN, produkční SMTP, monitoring,
aktualizace a otestované zálohování a obnova. Nikdy nezpřístupňujte Mailpit ani
databázi veřejně.
