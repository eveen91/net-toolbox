# Tenanty w net::toolbox

Tenant jest granicą danych organizacji lub klienta dla całej aplikacji.
Konto użytkownika jest globalne i może należeć do wielu tenantów, z inną rolą
w każdym z nich. DC i VRF pozostają przyszłymi strukturami wewnątrz tenanta.

## Obsługa

1. Zaloguj się jako administrator platformy (`admin`).
2. Otwórz **Config Panel → Tenants** i utwórz tenanta.
3. Wybierz go w polu **Tenant** na pasku aplikacji.
4. W tym samym panelu przypisz istniejące konto i rolę. Nowe konta tworzysz
   w zakładce **Users**, a szablony uprawnień w **Roles**.

`admin` jest rolą administratora platformy: zarządza kontami, rolami i wszystkimi
tenantami. `tenant-admin` zarządza istniejącymi członkami swojego tenanta i ma
pełny dostęp do jego narzędzi; nie otrzymuje administracji platformą. Pierwszy
dostęp kolejnych kont nadaje administrator platformy. Role niestandardowe mają
te same uprawnienia modułów co wcześniej, ale obowiązują w przypisanym tenancie.
Zmiana szablonu roli dotyczy wszystkich członkostw używających tego szablonu.

## Dane i zgodność

- `server/auth.db`: globalne konta, sesje, ustawienia, role, tenanty, członkostwa
  oraz audyt tworzenia tenantów i zmian dostępu.
- `server/toolbox.db`: dotychczasowe dane, przypisane bez kopiowania do tenanta
  **Domyślny** (`default`).
- `server/tenants/<UUID>/toolbox.db`: dane nowego tenanta. Katalog nadrzędny
  można ustawić przez `TENANT_DATA_ROOT`.
- Docker ustawia `TENANT_DATA_ROOT=/data/tenants` w trwałym wolumenie.

Przy pierwszej migracji istniejące konta zachowują role w tenancie domyślnym.
Migracja jest jednokrotna: ponowny start nie odtwarza cofniętych członkostw.
Nowe konta lokalne i AD otrzymują początkowe członkostwo w tenancie domyślnym.
Zmiana dawnej roli konta aktualizuje to członkostwo tylko wtedy, gdy nadal
odpowiada ono dawnej roli; niezależne przypisania tenantowe pozostają zachowane.

IPAM (w tym ustawienia, tagi, archiwum i audyt), routing, urządzenia,
Device Visualization (switche, firewalle, karty NIC, porty i historia),
audyt diagnostyki oraz dane walidacji korzystają z bazy aktywnego tenanta.
Podsieci, adresy i nazwy urządzeń mogą się powtarzać między tenantami.
Kalkulatory działające wyłącznie w przeglądarce nie wymagają osobnej bazy i
korzystają z globalnych uprawnień konta.

Tryb bez logowania zachowuje otwarty dostęp wyłącznie do tenanta domyślnego.
Pozostałe tenanty zawsze wymagają sesji i uprawnień. Zalogowane konta podlegają
członkostwu także przy wyłączonym globalnym wymogu logowania.

## API i nowe moduły

`X-Tenant-ID` wybiera tenanta; brak nagłówka zachowuje `default` dla zgodności
z istniejącymi klientami API. Strumienie SSE używają parametru `tenant_id`,
ponieważ natywny EventSource nie przesyła własnych nagłówków. Oba selektory
przechodzą tę samą kontrolę sesji i aktualnego członkostwa po stronie serwera.
Ścieżka pliku powstaje z rejestru i UUID, nigdy z nazwy podanej przez klienta.

Frontend przechowuje wybór osobno w każdej karcie. Zmiana tenanta ponownie
weryfikuje sesję i odmontowuje narzędzia, usuwając ich lokalny stan oraz SSE.

Nowy zapisujący moduł powinien korzystać z `db.get_connection()` lub wspólnego
resolvera `tenancy.context.database_path`, a jego inicjalizacja musi zostać
dodana do `tenancy.service.initialize_tenant`. Nie wolno przełączać globalnego
`DB_PATH` w trakcie żądań. Wątki wymagają `tenancy.context.run_in_executor`,
a zadania platformowe jawnego `tenant_scope`. Harmonogram IPAM iteruje po
zarejestrowanych tenantach; zadania dziedziczą właściwy kontekst.

## Migracje, backup i odtwarzanie

Start aplikacji wykonuje inicjalizację/migracje modułów w każdej zarejestrowanej
bazie. Utworzenie tenanta publikuje wpis w rejestrze dopiero po pomyślnym
utworzeniu schematów; zwykły błąd usuwa niedokończony katalog i wycofuje wpis.
Nagłe przerwanie procesu może pozostawić niezarejestrowany katalog UUID;
nie jest on udostępniany ani automatycznie dołączany do aplikacji.

Przed aktualizacją zachowaj kopię `auth.db`, `toolbox.db` i całego katalogu
`TENANT_DATA_ROOT`. Najprostszy spójny backup wykonasz przy zatrzymanym backendzie;
SQLite Backup API pozwala kopiować pojedynczą działającą bazę, ale spójny zestaw
wielu baz wymaga wstrzymania zapisów lub skoordynowanego snapshotu.
Przykłady backupu i kontrole po aktualizacji opisuje [procedura utrzymania serwera](maintenance.md).
Odtwarzanie wymaga zachowania UUID i zgodności rejestru z katalogami.
Nie przywracaj samej bazy danych tenanta pod identyfikatorem innego tenanta.

Nie ma automatycznego usuwania tenantów ani raportów przekrojowych. Oddzielne
pliki zapewniają granicę danych aplikacji; backend i administrator hosta nadal
mają dostęp do wszystkich plików. To nie są osobne procesy ani konta systemowe.

### Przenoszenie hostów Routing Map

Wybierz zapisany host w Routing Map, użyj **Move to tenant**, wybierz tenant docelowy,
następnie **Review move** i **Confirm move**. Można w ten sposób przenieść istniejące
hosty z „Domyślnego”, razem z trasami i interfejsami. Wymagane jest zalogowane konto
z dostępem do Routing Map w obu tenantach. Przenoszenie zachowuje datę zapisu,
usuwając host ze źródła; istniejący host o tej samej nazwie w celu blokuje operację.
Zmiana danych po podglądzie wymaga ponownego sprawdzenia. Audyt zapisuje operację
w obu tenantach. Blok hosta jest też usuwany z lokalnego pola importu, aby kolejny
zapis nie odtworzył przeniesionego hosta w źródle.

Dane i audyt są zapisywane w jednej transakcji SQLite obejmującej trzy pliki.
Przenoszenie wymaga trybu dziennika DELETE/TRUNCATE/PERSIST we wszystkich tych
bazach; przy WAL operacja jest odrzucana, ponieważ SQLite nie gwarantuje wtedy
atomowości transakcji obejmującej wiele plików ([SQLite ATTACH](https://www.sqlite.org/lang_attach.html)).

### Przenoszenie sieci IPAM

W szczegółach podsieci użyj **Move to tenant → Review move → Confirm move**.
Wymagane jest zalogowane konto z `ipam.write` (lub `ipam`/`*`) w obu tenantach.
Przenoszona jest wybrana podsieć wraz z całym drzewem podsieci podrzędnych,
metadanymi, adresami, tagami i ich przypisaniami, DHCP, rezerwacjami zakresów,
wykluczeniami skanów, historią skanów i ukończonymi zadaniami. Identyfikatory
rekordów są nadawane w bazie docelowej, a relacje zostają odpowiednio przepisane.
Sieć nadrzędna poza przenoszonym drzewem pozostaje w źródle.

Konflikt zakresu z dowolną siecią docelową, tag o tej samej nazwie i innych
metadanych, aktywny skan nakładającego się zakresu albo zmiana danych po podglądzie
blokuje przenoszenie. Harmonogramy skanowania są przenoszone jako **wyłączone**;
można je ponownie włączyć w nowym tenantcie. Archiwalne, usunięte rekordy oraz
wyciszenia kontroli jakości pozostają w źródle. Historia audytu jest kopiowana
do celu; jej oryginał i ślad przeniesienia pozostają w źródle. Operacja ma również
wpis w audycie obu tenantów. Wszystkie zmiany danych i audytu są jedną transakcją
z tymi samymi wymaganiami trybu dziennika SQLite co przenoszenie Routing Map.

## Wizualizacja urządzeń

[Device Visualization](device-visualization.md) zapisuje dane w bazie aktywnego
tenanta. Uprawnienie `device-visualization` jest nadawane przez role członkostw;
nie jest automatycznie dodawane do istniejących ról. Moduł obejmuje switche,
firewalle Check Point/FortiGate i generyczne serwery. Backup wszystkich baz
tenantów zawiera jego dane i audyt.
