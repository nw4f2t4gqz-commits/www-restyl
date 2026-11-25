# Restyl Drupal – lokální vývoj

Lokální Docker Compose stack obsahuje Composer-managed Drupal, MariaDB a Mailpit.
Konfigurace používá předem sestavený Drupal image z GHCR pro Synology s amd64.

## Stav projektu

Jde o lokální prototyp, nikoli hotovou kopii 1:1 ani připravené produkční
nasazení. Úvodní video je uložené lokálně; při omezení pohybu nebo nedostupnosti
videa se zobrazí statický obrázek. Video lze také pozastavit tlačítkem.
Je třeba dokončit vizuální porovnání, SEO
a kontrolu zachování rozložení při úpravách v editoru.
Dokumenty v patičce zatím odkazují na externí úložiště. Produkční SMTP,
příjemci formulářů a síťové zabezpečení administrace vyžadují ověření.

## Předpoklady

- Docker s Compose v2 a funkčním enginem (ověřeno s Docker 29.4.0 a Compose 5.1.1).
- Volné porty `127.0.0.1:8081` a `127.0.0.1:8026`.
- Přístup k Docker Hubu a GHCR; pro soukromý image přihlášení k GHCR
  s oprávněním `read:packages`.

Stack nezveřejňuje MariaDB port. Drupal a Mailpit UI naslouchají jen na loopbacku;
SMTP Mailpitu není publikované na host portu. Výchozí databázové údaje jsou
neprodukční a určené výhradně pro lokální vývoj. Lokální Apache přidává hlavičku
`X-Robots-Tag: noindex, nofollow`; pro produkci je nutná samostatná konfigurace.

## První spuštění

V kořeni projektu:

```sh
cp -n .env.example .env
docker compose config --quiet
docker compose up -d
docker compose ps
```

Následující instalaci spusťte **jen nad novou prázdnou databází**. `site:install
-y` může přepsat existující web. Použijí se DB proměnné předané do kontejneru:

```sh
docker compose exec drupal sh -lc \
  'vendor/bin/drush site:install standard -y \
    --db-url="mysql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}" \
    --site-name="Restyl (local)"'
```

Drush (`drush/drush` 13.x) je Composer závislost. Drupal core obsahuje
Symfony Mailer plugin; lokální `settings.php` přepíná defaultní mail interface
na `symfony_mailer` a nastavuje SMTP DSN na `mailpit:1025`. Zprávy se zobrazí na
`http://127.0.0.1:8026` a nemají veřejný relay. Drupal MailManager tak používá
stejný Mailpit transport. Konfigurace `system.mail:mailer_dsn` je strukturované
pole (`scheme`, `host`, `port`), nikoli DSN string.

### Česká administrace

Po první instalaci povolte core moduly, přidejte jazyk a stáhněte/importujte
aktuální překlady:

```sh
docker compose exec drupal vendor/bin/drush pm:enable language locale -y
docker compose exec drupal vendor/bin/drush language:add cs
docker compose exec drupal vendor/bin/drush config:set system.site default_langcode cs -y
docker compose exec drupal vendor/bin/drush config:set language.negotiation url.prefixes.cs '' -y
docker compose exec drupal vendor/bin/drush cache:rebuild
```

Ověřeno na Drupal 11.4.12 / Drush 13.8.1: `language:add cs` přidá češtinu,
stáhne překlad z Drupal translation serveru a importuje jej; při ověřovacím
běhu bylo importováno 4 321 řetězců. `locale:check` a
`locale:update --langcodes=cs -y` slouží k pozdějším aktualizacím. Drush příkazy
jsou součástí Drush 13; nic se nestahuje z produkčního Restyl webu.

U existujících účtů nastavte v profilu „Administration pages language“ na
Čeština. U standardního účtu vytvořeného při `site:install` (uid 1) lze
preferovaný jazyk administrace nastavit také; pro jiný účet nahraďte `1` jeho
UID:

```sh
docker compose exec drupal vendor/bin/drush php:eval \
  '$u = \Drupal\user\Entity\User::load(1); foreach (["preferred_langcode", "preferred_admin_langcode"] as $field) { if ($u->hasField($field)) { $u->set($field, "cs"); } } $u->save();'
```

Tento výchozí postup je opakovatelný na nové lokální instalaci; `language:add cs`
spusťte jen pokud jazyk ještě není přidán. Pro kontrolu dostupných aktualizací:

```sh
docker compose exec drupal vendor/bin/drush locale:check
docker compose exec drupal vendor/bin/drush locale:update --langcodes=cs -y
```

Lokální proměnné `RESTYL_MAIL_FROM`, `RESTYL_MAIL_TO_ELEKTRO` a
`RESTYL_MAIL_TO_ENERGY` se předávají do PHP kontejneru. `.env.example` používá
adresy `example.test`, které jsou vyhrazené pro příklady; Mailpit je pouze
zachytává. Bez nakonfigurovaných platných adres má vlastní modul odeslání
odmítnout a nehlásit úspěch. Hash salt Drupal instalace se při prvním startu
vygeneruje náhodně a uchovává se v privátním Docker volume `drupal_private`.

### Téma, redakce a počáteční obsah

Na nové instalaci s nastavenou češtinou vytvořte typ stránky, zapněte téma a
nahrajte omezený textový formát. Formát se smí importovat tímto postupem pouze
tehdy, pokud `restyl_html` ještě neexistuje. Modul vytváří roli redaktora,
menu, patičku a kontaktní formuláře:

```sh
docker compose exec drupal vendor/bin/drush recipe /var/www/html/web/core/recipes/page_content_type -y
docker compose exec drupal vendor/bin/drush theme:enable restyl -y
docker compose exec drupal vendor/bin/drush config:set system.theme default restyl -y
docker compose exec drupal vendor/bin/drush config:import --partial --source=/var/www/html/scripts/format -y
docker compose exec drupal vendor/bin/drush pm:enable restyl_site -y
docker compose exec drupal vendor/bin/drush cache:rebuild
```

`scripts/` a `content/` se připojují do kontejneru pouze pro čtení. Import se
nespouští automaticky. Nejprve ověřte dry-run a potom spusťte import:

```sh
docker compose exec -e RESTYL_IMPORT_DRY_RUN=1 drupal \
  vendor/bin/drush php:script scripts/import_into_drupal.php
docker compose exec drupal vendor/bin/drush php:script scripts/import_into_drupal.php
```

Import vypíše systémovou cestu vytvořené úvodní stránky `/node/N`; po její
kontrole nastavte v následujícím příkazu skutečné ID místo `N`:

```sh
docker compose exec drupal vendor/bin/drush config:set system.site page.front /node/N -y
docker compose exec drupal vendor/bin/drush cache:rebuild
docker compose exec drupal vendor/bin/drush cron
```

Cron vytvoří vyhledávací index. Pro pravidelnou aktualizaci indexu po úpravách
obsahu je nutné zajistit pravidelné spouštění Drupalu cronem; samotný Compose
plánovač neobsahuje.
Na instalaci vytvořené před přidáním závislosti `search_node` je nejprve nutné
spustit `docker compose exec drupal vendor/bin/drush pm:enable search_node -y`
a poté cron.
Na starší instalaci povolte vyhledávání přihlášeným uživatelům také příkazem
`docker compose exec drupal vendor/bin/drush role:perm:add authenticated 'search content'`.
Pro zobrazení administrační navigace a tématu dříve vytvořeným redaktorům spusťte
`docker compose exec drupal vendor/bin/drush role:perm:add restyl_editor 'access navigation'`
a `docker compose exec drupal vendor/bin/drush role:perm:add restyl_editor 'view the administration theme'`.
Po aktualizaci kódu existující instalace spusťte databázové aktualizace pomocí
`docker compose exec drupal vendor/bin/drush updatedb -y` a obnovte cache.
Pro nahrávání obrázků musí existující instalace převzít také aktualizovaný
formát a editor ze `scripts/format/`. Před částečným importem porovnejte jejich
aktivní konfiguraci: import přepíše místní změny těchto dvou konfigurací.

Přístup správce obnovíte lokálně příkazem:

```sh
docker compose exec drupal vendor/bin/drush user:login --uri=http://127.0.0.1:8081
```

Otevřete v prohlížeči vygenerovaný odkaz začínající `http://127.0.0.1:8081/`;
jednorázový přihlašovací odkaz nesdílejte.
Další informace jsou v [návodu importu](scripts/README.md) a
[návodu pro redakci](docs/redakce.md).

## Opakované spuštění a data

Po první instalaci stačí `docker compose up -d`. Drupal kód a závislosti jsou
součástí image z GHCR. Databáze, uploady a Mailpit
zprávy jsou uloženy v oddělených Docker named volumes:

- `restyl-local_mariadb_data`
- `restyl-local_drupal_files`
- `restyl-local_drupal_private`
- `restyl-local_mailpit_data`

Obnova image bez odstranění dat:

```sh
docker compose pull drupal
docker compose up -d --no-deps drupal
```

Na Synology zachovejte původní název projektu Container Manageru a jeho `.env`;
jiný název projektu může vytvořit nové prázdné volumes.

Zastavení bez ztráty dat:

```sh
docker compose down
```

`docker compose down -v` odstraní datové volumes; používejte pouze
pro záměrný reset vývojového prostředí.

## Záloha a obnova

Zálohovací skripty v `ops/` ukládají do `backups/` tři ověřitelné archivy:
dump MariaDB, Drupal `sites/default/files` a privátní volume s hash saltem.
Zálohy obsahují citlivá data, mají lokálně omezená oprávnění a jsou v `.gitignore`.
Nejde o off-site zálohu; důležité kopie bezpečně přeneste mimo tento počítač.
Při záloze zastavte importy a jiné zápisy, aby databáze a soubory odpovídaly
stejnému okamžiku. Kód/Composer image, Mailpit zprávy a Compose env nejsou součástí
zálohy.

```sh
./ops/backup.sh
```

Obnova vyžaduje konkrétní adresář zálohy a záměrný `--confirm`. Před výměnou
databáze automaticky vytvoří bezpečnostní zálohu současného stavu. Drupal se po
dobu obnovy zastaví; databáze se nahradí, soubory se obnoví překrytím (žádné
extra soubory se nemažou) a obnoví se původní hash salt:

```sh
./ops/restore.sh backups/restyl-YYYYMMDDTHHMMSSZ --confirm
```

Skripty standardně používají `.env.example` a Compose projekt `restyl-local`,
stejně jako lokální vývojový stack. Pro jiný lokální env soubor nebo název
Compose projektu nastavte `COMPOSE_ENV_FILE` či `COMPOSE_PROJECT_NAME`. Obnova
je určena pouze pro důvěryhodné archivy vytvořené tímto skriptem a stejný název
databáze.

## Vlastní kód

Místo pro vlastní téma je `web/themes/custom/restyl` a pro vlastní modul
`web/modules/custom/restyl_site`. Obsah je výslovně vyňat z `.gitignore`, zatímco
Drupal core/contrib zůstávají ignorované. Dockerfile při sestavení zkopíruje oba
adresáře do image, pokud existují. Po změně kódu sestavte a publikujte nový
image pro amd64 a upravte jeho tag v Compose. Importní snapshot a skripty se
naopak připojují z hosta read-only.

## Porty a nastavení

Výchozí host porty jsou 8081 (Drupal) a 8026 (Mailpit UI), vybrané tak, aby
nekolidovaly s běžnými službami na 8080 a 8025. Změnit je lze v `.env`. Bind
adresy zůstávají standardně `127.0.0.1`; nenastavujte je na `0.0.0.0`, pokud
nechcete službu zpřístupnit v síti.

Za HTTPS reverzní proxy nastavte `RESTYL_REVERSE_PROXY_ADDRESS` na IP adresu,
ze které proxy přichází do kontejneru. Drupal důvěřuje pouze hlavičce
`X-Forwarded-Proto` od této adresy; proxy ji musí přepisovat podle skutečného
protokolu a přístup k originu musí zůstat omezený. Po změně Docker sítě ověřte
adresu znovu. Bez nastavení proměnné zůstává podpora proxy vypnutá.

Před nasazením mimo lokální vývoj nahraďte databázová hesla bezpečnými tajemstvími
a zajistěte TLS, zálohování, aktualizace a správnou konfiguraci poštovního
serveru. Tato Compose konfigurace není produkční deployment.

### Povinná bezpečnostní brána před nasazením

**Produkce není tímto základem ani ověřena, ani označena za zabezpečenou.**
Konkrétní reverzní proxy, DNS a síťová topologie zatím nejsou známy; Compose
proto záměrně neobsahuje jejich pravidla ani nevystavuje služby na veřejné
rozhraní. Nasazení zůstává blokováno, dokud provozovatel neprokáže přístup
k administraci pouze z LAN/VPN na skutečné hranici sítě.

Před otevřením provozu musí být splněno a otestováno:

1. Zvolit konkrétní proxy/ingress a vynutit LAN/VPN politiku pro přihlašování,
   administraci a veškeré změny obsahu. Pouhé blokování `/admin` nestačí:
   zahrnout mimo jiné `/user/login`, `/user/*/edit`, `/node/*/edit`,
   formuláře, AJAX/JSON rozhraní a další routy s oprávněním měnit data.
   Pokud nelze úplnost path/routing pravidel doložit, omezit přes LAN/VPN celý
   web.
2. Na firewallu omezit přímý přístup k originu tak, aby jej nebylo možné obejít
   připojením mimo proxy; používat TLS na veřejné i interní hranici podle
   topologie a nepovažovat DNS za řízení přístupu.
3. Z nezpůsobilé veřejné sítě ověřit, že přihlášení i reprezentativní i
   alternativní zápisové cesty jsou odmítnuté, a z LAN/VPN ověřit, že oprávnění
   řádně fungují. Zahrnout také různé metody HTTP a přímý přístup k originu.
4. Zaznamenat použitou proxy, povolené sítě, testovací URL a výsledek; po změně
   rout, modulů, proxy nebo DNS test zopakovat.

Drupal role a oprávnění jsou další vrstva, nikoli náhrada síťového omezení.
Dokud tato brána není dokončena, nepovažovat administraci ani produkci za
zabezpečenou.
