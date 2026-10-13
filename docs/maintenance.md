# Aktualizacje i utrzymanie serwera

Procedura dotyczy aktualizacji pakietów systemowych (`apt upgrade`) oraz
ponownego uruchomienia net::toolbox. Zmiana wersji aplikacji może dodatkowo
uruchomić migracje przy starcie backendu; dlatego kopia danych powinna powstać
przed pierwszym uruchomieniem nowej wersji.

## Wpływ pakietów systemowych

| Pakiety | Znaczenie dla projektu | Sprawdzenie po aktualizacji |
|---|---|---|
| `python3.13`, `libpython3.13-*`, `python3.13-venv` | Interpreter i biblioteka standardowa backendu; lokalne `venv` może korzystać z systemowego interpretera przez symlink | Wersja interpretera, importy i start API |
| `libsqlite3-0` | Obsługa baz aplikacji, kont i tenantów przez `sqlite3` | Integralność baz i odczyt danych |
| `libssl3t64`, `openssl`, `openssl-provider-legacy` | TLS i komponenty kryptograficzne; zależności mogą korzystać też z bibliotek dołączonych do swoich pakietów | Logowanie AD/LDAPS, HTTPS i używane połączenia SSH |
| `libc6`, `libc-bin` | Biblioteki systemowe wykorzystywane przez interpreter i rozszerzenia natywne | Restart procesów aplikacji i kontrola logów |
| `linux-image-amd64` | Jądro hosta | Restart hosta, dostęp sieciowy i ponowny start aplikacji |
| `bind9-*`, `dhcpcd-base`, `curl`, `libcurl*` | Narzędzia DNS/HTTP oraz konfiguracja sieci hosta | DNS, adres hosta i dostęp do urządzeń |
| `tzdata` | Strefy czasowe systemu | Poprawność wyświetlanych dat; znaczniki aplikacji są zapisywane w UTC |

Aktualizacja w obrębie tej samej gałęzi Pythona zwykle pozwala zachować `venv`.
Pakiety zainstalowane przez `pip` nie są aktualizowane przez `apt`.
Po zmianie gałęzi, np. 3.13 → 3.14, przygotuj nowe środowisko i zweryfikuj
zależności. Nie łącz rutynowego upgrade systemu z przypadkowym upgrade wszystkich
pakietów `pip`. Zasady działania środowisk opisuje [dokumentacja Python venv](https://docs.python.org/3.13/library/venv.html).

Weryfikacja z 2026-10-12 dla lokalnego hosta wykazała aktualizacje Debiana 13:
Python `3.13.5-2+deb13u4 → deb13u5`, SQLite `3.46.1-7+deb13u1 → deb13u2`,
OpenSSL `3.5.6 → 3.5.7`. Importy zależności działały przed aktualizacją.
To zapis oceny konkretnego zestawu pakietów, a nie potwierdzenie poprawności
systemu po upgrade ani stałe wymagania projektu.

## Przed aktualizacją

1. Sprawdź proponowane zmiany przez `apt list --upgradable` i `apt-cache policy`.
2. Sprawdź sposób uruchamiania backendu i frontendowego serwera. Polecenie
   `uvicorn` uruchomione ręcznie nie zapewnia automatycznego startu po reboot.
   Timer `ipam-scan-all.timer` uruchamia klienta skanowania, a nie serwer API.
3. Poczekaj na zakończenie skanów i przenoszenia danych między tenantami.
   Wstrzymaj zewnętrzne zadania zapisujące do baz oraz timer skanowania, jeżeli
   jest używany. Zatrzymaj wszystkie procesy backendu zwykłym sposobem ich obsługi.
4. Zrób spójny backup poniższych danych i zachowaj konfigurację uruchomienia,
   w tym wartość `TENANT_DATA_ROOT` oraz używaną wersję kodu.

### Backup instalacji lokalnej

Obejmuje `server/auth.db`, `server/toolbox.db` i cały katalog tenantów z UUID.
Domyślnie jest to `server/tenants`; własną ścieżkę ustal z konfiguracji backendu.
Nie zakładaj, że zmienne usługi są dostępne w bieżącej powłoce.

Przykład dla Bash, z katalogu głównego repozytorium, **po zatrzymaniu wszystkich
procesów zapisujących do baz**. Dostosuj katalog backupu i katalog tenantów.
Nie wykonuj tego wariantu na ścieżkach będących symlinkami do wolumenu Docker.

```bash
set -euo pipefail
umask 077
backup_dir="/var/backups/net-toolbox/$(date -u +%Y%m%dT%H%M%SZ)"
tenant_data_dir="${TENANT_DATA_ROOT:-$PWD/server/tenants}"
mkdir -p "$backup_dir"
cp -a server/auth.db server/toolbox.db "$backup_dir/"
# Zachowaj także istniejące pliki dziennika, np. po awaryjnym zatrzymaniu.
for database_file in server/auth.db server/toolbox.db; do
  for suffix in -wal -shm -journal; do
    if [ -f "${database_file}${suffix}" ]; then
      cp -a "${database_file}${suffix}" "$backup_dir/"
    fi
  done
done
if [ -d "$tenant_data_dir" ]; then
  cp -a "$tenant_data_dir" "$backup_dir/tenants"
fi
```

Brak katalogu tenantów jest normalny, jeśli istnieje tylko tenant domyślny.
Jeśli rejestr zawiera inne tenanty, brak ich plików jest błędem wymagającym
wyjaśnienia przed uznaniem backupu za kompletny. Kopia zawiera konta, sesje
i konfigurację uwierzytelniania; przechowuj ją z ograniczonym dostępem.

Kopiowanie działających plików przez `cp` nie jest procedurą backupu online.
[SQLite Backup API](https://www.sqlite.org/backup.html) zapewnia poprawną kopię
pojedynczej bazy, ale kolejne kopie kilku baz nie gwarantują wspólnego punktu
w czasie. Dla spójności rejestru tenantów i przenoszenia danych wstrzymaj zapisy
na czas wykonania całego zestawu albo użyj skoordynowanego snapshotu storage.

### Instalacja Docker

Dane znajdują się w wolumenie `net-toolbox-data`: `/data/auth.db`,
`/data/toolbox.db` i `/data/tenants/<UUID>/toolbox.db`. Zatrzymaj backend
(`docker compose -f docker/docker-compose.yml stop backend`) i zarchiwizuj
**cały wolumen**, zachowując strukturę katalogów oraz prawa dostępu.
Własny `TENANT_DATA_ROOT` poza tym wolumenem wymaga osobnego backupu.

Upgrade pakietów hosta nie aktualizuje bibliotek wewnątrz istniejącego obrazu.
Aktualizacja tych bibliotek wymaga przebudowania obrazu z aktualną bazą,
następnie odtworzenia kontenerów z zachowaniem wolumenu danych.

## Aktualizacja i uruchomienie

Wykonaj zaplanowane `apt update` i `apt upgrade`, przejrzyj komunikaty dotyczące
konfiguracji i restartów usług. Po zmianie Pythona, OpenSSL lub libc uruchom
backend ponownie. Po aktualizacji jądra uruchom host ponownie, aby załadować nowe
jądro. Upewnij się, że backend i frontend zostały uruchomione po reboot.

Dla ręcznie uruchamianego backendu, z katalogu głównego repozytorium:

```bash
cd server
./venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Przy uruchamianiu przez usługę użyj jej faktycznej nazwy i zachowaj ustawione
zmienne środowiskowe. Repozytorium nie definiuje uniwersalnej usługi systemd
uruchamiającej backend. Przywróć wcześniej wstrzymane timery dopiero po kontroli API.

## Kontrola po aktualizacji

Poniższe polecenia uruchom z katalogu głównego repozytorium. Nie zmieniają danych:

```bash
server/venv/bin/python3 -c 'import sys, sqlite3, ssl; print(sys.version); print("SQLite", sqlite3.sqlite_version); print(ssl.OPENSSL_VERSION)'
server/venv/bin/python3 -c 'import fastapi, uvicorn, paramiko, netmiko, bcrypt, cryptography, ldap3, winrm; print("Importy backendu: OK")'
curl --fail --show-error http://127.0.0.1:8000/api/health
```

Oczekiwana odpowiedź health to `{"status":"ok"}`. Potwierdza ona dostępność
procesu API; nie sprawdza baz, uprawnień tenantów ani połączeń z urządzeniami.
Dla kontenerów importy sprawdzaj wewnątrz kontenera backendu.

Sprawdź również:

- logi startu: brak błędów importu, inicjalizacji baz i migracji;
- integralność **każdej** bazy: `PRAGMA integrity_check` powinno zwrócić `ok`,
  a `PRAGMA foreign_key_check` nie powinno zwrócić żadnych wierszy;
- logowanie lokalne i AD/LDAPS, jeżeli jest skonfigurowane;
- przełączanie tenantów oraz dostęp do oczekiwanych danych IPAM i Routing Map;
- izolację danych i uprawnienia zwykłego użytkownika;
- używane połączenia SSH/WinRM/HTTPS i DNS, z uwzględnieniem dostępu do urządzeń;
- harmonogramy IPAM: brak nieoczekiwanych skanów lub błędów uruchamiania.

Kontrolę integralności wykonuj w trybie SQLite tylko do odczytu, na rzeczywistych
plikach ustalonych z rejestru i konfiguracji. Zwykłe otwarcie błędnej ścieżki
może utworzyć pustą bazę i ukryć pomyłkę. Nie testuj przenoszenia rzeczywistych
sieci lub hostów jako próby technicznej; użyj danych testowych.

Przenoszenie danych między tenantami wymaga trybu dziennika SQLite
DELETE/TRUNCATE/PERSIST we wszystkich uczestniczących bazach. Nie przełączaj ich
na WAL jako element rutynowej aktualizacji. Szczegóły: [tenanty i przenoszenie danych](tenants.md).

## W razie problemów

Najpierw sprawdź wersję interpretera, ścieżkę `venv`, konfigurację i logi.
Przy zmianie gałęzi Pythona zbuduj osobne środowisko z `server/requirements.txt`
i sprawdź działanie przed przełączeniem backendu. Ostrzeżenie deprecacji samo
w sobie nie oznacza błędu importu lub niedostępności API.

Jeśli konieczne jest odtworzenie danych, zatrzymaj wszystkie procesy zapisujące
i zachowaj także kopię stanu po awarii. Odtwórz cały spójny zestaw `auth.db`,
`toolbox.db` i katalogów tenantów z oryginalnymi UUID, zachowując uprawnienia
systemowego konta backendu. Nie mieszaj baz z różnych momentów ani nie zostawiaj
plików WAL/journal z innego stanu. Dobierz wersję aplikacji zgodną z przywróconym
schematem; uruchomienie backendu może ponownie wykonać migracje. Przed wznowieniem
zapisów przeprowadź powyższą kontrolę.
