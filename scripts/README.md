# Veřejný obsah Restyl → Drupal 11

Import vychází pouze z veřejného server-renderovaného HTML `https://www.restyl.cz/`
a veřejné XML sitemap. Nestahuje WordPress REST API, nespouští stažený JavaScript,
nepoužívá přihlašovací údaje a neodesílá žádné formuláře. Importovanými položkami
jsou editovatelné uzly typu **Basic page**, s původním titulkem a cestou.

## Vytvoření/obnova snapshotu

Z kořene projektu:

```sh
python3 scripts/import_public_content.py --fetch
python3 scripts/import_public_content.py --check
```

První příkaz vytvoří `content/pages.json` a `content/assets/`. Stránky jsou
sanitizované na bezpečné HTML; skripty, styly, formulářová pole, vložené rámy,
událostní atributy a nebezpečné URL se zahazují. Zachovávají se pouze výslovně
povolené strukturální třídy (včetně `vc_row`, `vc_col-md-1` až `vc_col-md-12`,
`wpb_wrapper` a `rev_slider_wrapper`); všechny ostatní třídy a atributy se
zahazují. Seznam určuje `ALLOWED_CLASSES` v Python skriptu a Drupal filtr
v `format/filter.format.restyl_html.yml`. Odkazy na původní interní
stránky se převedou na lokální cesty. Formuláře se nespouštějí ani nekopírují:
pouze původní Contact Form 7 (třída `wpcf7-form`) se nahrazuje jasným odkazem
na `/formular/elektro` nebo `/formular/energy`. Vyhledávací a ostatní
nerozpoznané formuláře se přeskočí, nepředstírají kontaktní formulář a uvádějí
se v `warnings` v `content/pages.json`. Vyhledávání musí případně dodat Drupal
nebo téma.

Existující snapshot se bez výslovného `--force` nepřepisuje. Obnova je:

```sh
python3 scripts/import_public_content.py --fetch --force
python3 scripts/import_public_content.py --check
```

Refresh nemění existující soubory médií; nová verze souboru dostane nové jméno
podle kontrolního součtu. Staré soubory se automaticky nemažou.

## Import do lokálního Drupalu

Importer vyžaduje nabootstrapovaný Drupal 11, typ obsahu Basic page (`page`),
bezpečný formát `restyl_html` popsaný níže, Drush a přístup k lokálnímu úložišti.
Neinstaluje ani nemění formát, role nebo `system.site`. Před ostrým během
zkontrolujte dry-run. V aktuálním Compose jsou `scripts/` i `content/`
připojeny do kontejneru jen pro čtení; z kořene projektu:

```sh
docker compose exec -e RESTYL_IMPORT_DRY_RUN=1 drupal \
  vendor/bin/drush php:script scripts/import_into_drupal.php
docker compose exec drupal vendor/bin/drush php:script scripts/import_into_drupal.php
```

Lze též použít `vendor/bin/drush php:script scripts/import_into_drupal.php`
z kořene projektu, pokud je Drupal dostupný přímo v tomto prostředí. Pro
nestandardní umístění manifestu lze nastavit `RESTYL_IMPORT_MANIFEST`.

### Formát a redakční oprávnění

Import vytváří standardní uzly typu `page` (Basic page); pole `body` používá
textový formát `restyl_html`, nikdy `basic_html` ani `full_html`. Obsah je před uložením
sanitizován a obrázky/PDF jsou běžné lokální odkazy, takže uzly lze upravovat
Drupal editorem bez speciálního shortcode filtru. Formulářové odkazy jsou
obyčejné odkazy na cesty modulu `/formular/elektro` a `/formular/energy`.

Přesný návrh konfigurace bez neomezeného HTML je ve dvou souborech
`scripts/format/filter.format.restyl_html.yml` a
`scripts/format/editor.editor.restyl_html.yml`. Zapíná core filtr `filter_html`
s taxativním seznamem tagů, atributů a hodnot `class`, filtr zabezpečení obrázků
a CKEditor 5 včetně **Source Editing** a tabulek. Nevytváří oprávnění. Source
Editing dovoluje tentýž omezený seznam tříd; nepovoluje `style`, `on*`, obecné
`data-*`, `script` ani iframe. Pro vazbu nahraných obrázků na soubory jsou
povoleny pouze jejich atributy `data-entity-uuid` a `data-entity-type`.
CKEditor umožňuje nahrát JPEG, PNG a GIF do 5 MB. Třídy zachovává prostřednictvím General
HTML Support; složité bloky je vhodné upravovat v režimu zdroje, nikoli nutně
vizuálním editorem. Není zaručeno, že každé libovolné přeskupení struktury
vizuálním editorem zachová původní HTML: před redakčním nasazením ověřte
round-trip na kopii každého typu stránky.

Správce může po revizi návrh explicitně aplikovat na kompatibilní instalaci
s povolenými moduly Filter, Editor a CKEditor 5 (částečný import pouze těchto
dvou konfigurací; nepoužívat při existujícím `restyl_html` bez kontroly):

```sh
docker compose exec drupal vendor/bin/drush config:import --partial \
  --source=/var/www/html/scripts/format -y
```

Importer kontroluje, že aktivní `restyl_html` má přesně navržený allowlist;
při nesouladu ostrý běh odmítne. Pro jiné prostředí je třeba dodat oba YAML
soubory a následně synchronizovat konfiguraci dle jeho procesu. Kompatibilitu
návrhu lze zkontrolovat bez ukládání konfigurace nebo obsahu příkazem:

```sh
docker compose exec drupal vendor/bin/drush php:script scripts/test_drupal_format.php
```

Samotný import role ani oprávnění nemění. Aby redaktor mohl stránky skutečně
upravovat, správce musí roli `content_editor` přidělit Drupal oprávnění
**Edit any Basic page content** (nebo zajistit, že je vlastníkem uzlu a má
**Edit own Basic page content**) a **Use the Restyl bezpečný HTML text format**
(`use text format restyl_html`).
Názvy se mohou v administračním rozhraní mírně lišit podle překladu. Bez těchto
oprávnění mohou být stránky viditelné, ale formulář pro editaci nebo uložení
těla nebude redaktorovi dostupný. Nepovolujte kvůli tomuto importu `full_html`.

Importer nikdy nemaže uzly ani soubory. První běh vytvoří uzel pouze tehdy, když
jeho cesta není obsazena. Ukládá UUID a hash naposledy importovaných polí do
Drupal State; opakovaný běh nezměněný obsah přeskočí. Pokud někdo v Drupalu
změní titulek, tělo nebo alias, další běh stránku označí `CONFLICT` a ponechá ji
beze změny. Záměrně smazaný importovaný uzel se znovu nevytvoří. Aktualizuje se
jen stránka, jejíž importované hodnoty stále odpovídají poslednímu snapshotu;
aktualizace vytvoří revizi. Jakákoli nová revize znamená konflikt, i když
importovaná pole zůstala stejná. Záznamy starší verze importu bez informace
o revizi se pro jistotu označí jako konflikt a vyžadují ruční posouzení.

### Úvodní stránka a původní cesty

Drupal neobsluhuje úvodní stránku vytvořením aliasu `/`: ten se při ukládání
aliasu normalizuje na prázdný řetězec. Import proto pro veřejnou URL `/` vytvoří
běžný uzel bez kořenového aliasu a vypíše jeho systémovou cestu `/node/N`.
Nemění `system.site`. Po kontrole uzlu musí správce ručně nastavit:

```sh
docker compose exec drupal vendor/bin/drush config:set system.site page.front /node/N -y
docker compose exec drupal vendor/bin/drush cache:rebuild
```

`N` nahraďte ID vypsaným importem. Ostatní aliasy Drupal ukládá bez koncového
lomítka; veřejná cesta s koncovým lomítkem může být Drupalu přesměrována na
normalizovanou podobu. Import neobsazuje již existující aliasy.

Média se ukládají do `public://restyl-import/`, URL se při importu převedou na
konfigurovanou veřejnou cestu Drupalu. Existující soubor se nikdy nepřepisuje;
nesouhlasící hash import zastaví.

## Rozsah a limity snapshotu

- Aktuálně pořízený snapshot obsahuje všech 16 URL z veřejné sitemap a čtyři
  detaily `/portfolio/...`, které odkazuje stránka `/elektro/` (celkem 20).
- Snapshot stáhl 116 obrázků, všechny z `media.smtx.cz`; nebyl nalezen žádný
  odkaz na PDF **v importované oblasti `main`**, takže nebylo staženo žádné
  PDF. Importní `warnings` uvádějí přeskočené ne-kontaktní formuláře a případné
  problémy s médii pouze ve zpracované oblasti. Patička
  není importována a její následující dokumenty nemají lokální kopii; případné
  odkazy v tématu proto mohou stále záviset na externím `media.smtx.cz`:

  - [ISO 9001:2015](https://media.smtx.cz/file/media-b8a28-eu/s/768186e0fbc6/2019/03/f30dbe8f-restyl_iso_web.pdf?v=8bc998e6)
  - [GDPR ELEKTRO](https://media.smtx.cz/file/media-b8a28-eu/s/768186e0fbc6/2018/08/GDPR_RESTYL_ELEKTRO.pdf?v=3c66ef14)
  - [GDPR ENERGY](https://media.smtx.cz/file/media-b8a28-eu/s/768186e0fbc6/2018/08/GDPR_RESTYL_ENERGY.pdf?v=6baa234b)
  - [GDPR PLAN](https://media.smtx.cz/file/media-b8a28-eu/s/768186e0fbc6/2018/08/GDPR_RESTYL_ENERGY.pdf?v=6baa234b) — původní patička odkazuje na stejný soubor jako ENERGY; správnost je nutné ověřit.

  Patička obsahuje také externí odkazy na mapy.cz, obchodní rejstřík, Facebook
  a LinkedIn. Snapshot není bez připojení plně samostatný; odkazy a tyto PDF je
  třeba převést a ověřit samostatně, pokud mají být dostupné lokálně.
- Stahují se pouze obrázky a PDF nalezené v obsahu stránky, pokud jsou na
  `www.restyl.cz`, `restyl.cz` nebo `media.smtx.cz`, odpovídají deklarovanému
  MIME typu a projdou limity velikosti. SVG, videa, CSS pozadí a média na jiných
  hostech se nestahují. Nedostupná či nepodporovaná média jsou uvedena ve
  `warnings` v `content/pages.json`; externí běžné odkazy zůstávají odkazy.
- Import používá serverově vykreslenou část `main` / `content-container`, ne
  WPBakery shortcody ani téma WordPressu. Zachování tříd nestačí k plné vizuální
  shodě: inline styly, CSS pozadí, datové atributy a JavaScript slideru se
  nepřenášejí. Interakční prvky závislé na WordPress JavaScriptu (např. tlačítko
  v původním slideru) proto vyžadují ruční nahrazení a kontrolu tématem.
  Aktuální téma přehrává lokálně uložené úvodní video a při omezení pohybu
  nebo selhání přehrávání ponechá statický obrázek; po editaci úvodní stránky
  je nutné funkci zkontrolovat. Pozadí úvodního textového bloku s fotografií
  žárovky je samostatně uložené v tématu, protože importer CSS pozadí
  nestahuje.
  Import převádí původní boční panel `aside.col-md-3` na bezpečný
  `div.col-md-3`, aby jeho položky zůstaly ve společném sloupci.
- Veřejná sitemap poskytuje `lastmod`, nikoli datum vytvoření ani kompletní
  WordPress metadata. Je-li `lastmod` k dispozici, používá se jako nejbližší
  dostupné datum pro Drupal `created` (nejde zaručit, že jde o původní datum
  publikace); popis a zdrojová URL zůstávají ve snapshotu a importním stavu.
  Meta description nemusí být zobrazeno jako Drupal SEO metadata bez
  odpovídajícího modulu/pole.
- Cesty mimo sitemap a čtyři nalezené portfolio odkazy se automaticky
  neprocházejí. Počet stránek a stažených médií vypíše `--fetch`; kompletnost
  lokálních souborů kontroluje `--check`.

Automatické testy sanitizace:

```sh
python3 -m unittest scripts.test_import_public_content
docker compose exec drupal vendor/bin/drush php:script scripts/test_drupal_format.php
```
