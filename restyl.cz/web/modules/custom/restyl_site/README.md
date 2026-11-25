# Kontaktní formuláře RESTYL

Modul poskytuje formuláře `/formular/elektro` a `/formular/energy`.
Příjemci původních formulářů nejsou veřejně zjistitelní a musí je potvrdit
vlastník webu.

Pro odesílání je nutné nastavit e-mailový transport Drupalu a proměnné prostředí
`RESTYL_MAIL_FROM`, `RESTYL_MAIL_TO_ELEKTRO` a `RESTYL_MAIL_TO_ENERGY`.
Odesílatel musí být povolený u použitého SMTP poskytovatele. Pokud adresy
chybí nebo nejsou platné, formulář zprávu neodešle a zobrazí chybu. Nastavení
příjemců, přihlašovacích údajů ani hesel nepatří do verzovaných souborů.

Lokálně směrujte poštu výhradně do testovacího SMTP zachytávače. Před nasazením
ověřte nastavení produkčního SMTP a doručení na schválené adresy. Formulář
uchovává osobní údaje pouze v odeslaném e-mailu a používá základní omezení
počtu odeslání; provozovatel musí posoudit další ochranu proti spamu a aktuální
znění informací o zpracování osobních údajů.

Při instalaci modul vytvoří roli **Redaktor RESTYL** pro správu základních
stránek. Roli přidělujte pouze důvěryhodným zaměstnancům a administraci
zpřístupněte jen přes firemní síť nebo VPN. Běžným návštěvníkům tuto roli
nepřidělujte.
