# Device Visualization

Narzędzie służy do ręcznej dokumentacji fizycznych portów switchy, routerów, firewalli
Check Point/FortiGate, serwerów oraz macierzy z dwoma kontrolerami. Nie odpyta urządzenia, nie wymaga haseł i nie
pokazuje bieżącego stanu linku. Znacznik przy porcie oznacza zapisaną informację
„Leads to”, a nie aktywne połączenie sieciowe.

## Uprawnienia i tenanty

Dane oraz historia są przechowywane w bazie aktywnego tenanta. Wybierz tenanta na
pasku aplikacji, a następnie **Device Visualization**. W istniejącej instalacji
administrator musi nadać roli uprawnienie `device-visualization` w Config Panel.
Nowe instalacje dodają je do początkowej roli `user`; dotychczasowe role nie są
nadpisywane. Administrator platformy i `tenant-admin` mają dostęp przez `*`.

Nazwy urządzeń są unikalne bez rozróżniania wielkości liter według SQLite NOCASE
w ramach jednego tenanta, wspólnie dla wszystkich typów urządzeń. W innych
tenantach mogą istnieć te same nazwy. Wybór tenanta usuwa lokalne szkice edycji.
Tryb bez logowania zachowuje istniejące zasady dostępu do tenanta domyślnego.

## Tworzenie i porty

Urządzenia są wspólną ewidencją z [DC Inventory](dc-inventory.md). Formularz
**New device / Edit device → DC / rack location** zapisuje wysokość urządzenia
w U, szafę i początkowe U; centrum danych wynika z szafy. U1 znajduje się na dole,
a urządzenie 2U od U3 zajmuje U3–U4. Wysokość jest wymagana przy zapisie w UI,
również dla dotychczasowych urządzeń z nieznaną wysokością. Brak szafy oznacza
**Unassigned**. Kolizje i przekroczenie pojemności szafy są odrzucane.

Katalog centrów i szaf można odczytać z uprawnieniem `device-visualization`;
zarządzanie nimi wymaga `dc-inventory`. API urządzenia przyjmuje opcjonalne
`heightU`, `rackId`, `rackPosition`; pominięcie ich w edycji zachowuje lokalizację,
a `rackId: null` odpina urządzenie. Przypisanie w DC Inventory współdzieli wersję
urządzenia, więc równoczesne zapisy wymagają ponownego wczytania po konflikcie.
Położenie nie tworzy kopii urządzenia i zachowuje wszystkie dane jego portów.

1. Wybierz **New device**, typ i nazwę; opcjonalnie opis oraz własną nazwę modelu.
2. Switch/router/firewall: ustaw liczbę portów Ethernet, SFP i QSFP oraz prędkość każdej
   rodziny. Dla firewalla wybierz Check Point, FortiGate lub wariant generyczny.
3. Serwer: dodaj 1–16 kart NIC. Każda karta ma niezależny typ złącza, 1–8 gniazd,
   prędkość i opcjonalną nazwę. **Add network card** zajmuje pierwszy wolny slot.
4. Użyj **Save device**. Wybierz port na panelu, wpisz etykietę i **Leads to**, a
   następnie **Save assignment**. **Clear assignment** usuwa cel i zachowuje
   aktualną etykietę edytora.

Prędkości: Ethernet 1/10G, SFP 10/25G, QSFP 40/100G. Maksymalnie 128 portów DATA
oraz jeden opcjonalny port MGMT na urządzenie (macierz: dwa, po jednym na kontroler); switch/router: do 96 Ethernet, 48 SFP i 16 QSFP; firewall: do 96 Ethernet,
32 SFP i 16 QSFP. Wygląd firewalla
jest generyczny; wpisany model nie pobiera specyfikacji producenta. Serwer pokazuje
tylny panel i osobne sloty NIC. Na telefonie panel portów przewija się poziomo.

Wszystkie typy urządzeń mogą mieć osobne gniazdo **MGMT · Ethernet 1G** (macierz: po jednym na kontroler).
Pole **Dedicated management port (MGMT · Ethernet 1G)** jest domyślnie zaznaczone
w **New device**. Istniejące urządzenia pozostają bez zmian; port można dodać
w **Edit device**, zaznaczając to samo pole. MGMT nie zmienia numeracji portów DATA
ani slotów NIC. Etykietę, **Leads to**, adres IP i VLAN-y edytuje się w zwykłym edytorze portu.
Wyłączenie MGMT usuwa jego gniazdo; jeśli zawiera zapisane dane, wymaga istniejącego
podglądu strat i **Confirm removal and save**.

Router jest osobnym typem urządzenia, bez pola vendora. Typu zapisanego urządzenia
nie można zmienić. API przyjmuje `deviceType: "router"` z `portGroups`, bez
`networkCards` i bez vendora; obowiązują te same prędkości rodzin co dla switcha.

## Macierz: dwa kontrolery i osobne karty NIC

W **New device → Storage array** skonfiguruj osobno **Controller A** i
**Controller B**. Każdy wymaga 1–8 kart NIC w lokalnych slotach 1–8; każda karta
ma 1–8 portów, własną rodzinę złączy, prędkość i opcjonalną nazwę. Łączny limit
wynosi 128 portów DATA. NIC 1 może istnieć jednocześnie na obu kontrolerach.
Panel tylny pokazuje dwa oddzielne banki portów. Macierz nie ma vendora, a jej
zapisanego typu nie można zmienić.

Wspólne pole **Dedicated management ports (one per controller · Ethernet 1G)**
włącza lub wyłącza oba porty MGMT naraz: limit wynosi wtedy 128 DATA + 2 MGMT.
Adresy IP, etykiety, cele i VLAN-y obu portów MGMT edytuje się niezależnie w
istniejącym edytorze portu. Usunięcie lub wymiana karty kontrolera A z zapisanym IP, VLAN-em, etykietą lub celem
wymaga przeglądu utraconych danych i potwierdzenia; zachowane karty kontrolera B
utrzymują identyfikatory i przypisania.

API przyjmuje `deviceType: "storage"`, bez vendora, z `networkCards` zamiast
`portGroups`. Każda karta musi zawierać `controller: "A"` lub `"B"` i lokalne
`slotNumber` 1–8. Istniejący identyfikator karty nie może zmienić kontrolera ani
slotu; karta obcego urządzenia jest odrzucana. Odpowiedzi kart i portów zawierają
opcjonalne `controller`, puste dla innych typów urządzeń. Serwer nie przyjmuje
niepustego `controller`. Pominięte `managementPort` zachowuje dotychczasową
semantykę tworzenia i edycji; `true` tworzy parę MGMT.

## Routery, firewalle, macierze i serwery: panel oraz mapa połączeń

Po wybraniu routera, firewalla, macierzy lub serwera domyślny widok **Connections** pokazuje razem
kompaktowy panel fizyczny z **Fit** oraz mapę zapisanej dokumentacji:
interfejs → IP / opcjonalny VLAN → **Leads to**. IP i VLAN pozostają niezależne;
brak jednej informacji nie blokuje pozostałych. Kliknięcie interfejsu na mapie
lub gniazda otwiera istniejący edytor portu. Obie reprezentacje współdzielą zaznaczenie.

**Show interfaces** oferuje **With saved details** (etykieta, IP, VLAN lub cel),
**All interfaces** i **Management only**. MGMT jest pierwszy w swojej grupie; mapa pokazuje
12 interfejsów na stronę. **Find interface** wyszukuje nazwę/etykietę, IP, VLAN
oraz cel. Pusty wynik wyjaśnia brak danych lub dopasowań i udostępnia
**Show all interfaces**, które usuwa filtr wyszukiwania i pokazuje wszystkie porty.

Macierz grupuje interfejsy według kontrolera. Filtr **Controller** wybiera
**Both controllers**, **Controller A** lub **Controller B**; wyszukiwanie i zakres
interfejsów działają razem z tym filtrem. **Show all interfaces** resetuje również kontroler.

Wybór routera, firewalla, macierzy lub serwera zwija listę urządzeń; **Browse devices** przywraca ją.
Osobne widoki **Panel**, **Port table** i **History** pozostają dostępne.
Switche zachowują domyślny panel na desktopie oraz tabelę na wąskim ekranie.
Mapa dopasowuje układ do szerokości swojego kontenera; na telefonie zachowuje
pełnowymiarowy tekst i przyciski, a fizyczny podgląd ma wysokość 140px.
Linie i strzałki opisują zapisane **Leads to**, nie stan linku ani kierunek ruchu.

Serwer pokazuje tylny panel z kartami NIC obok siebie i osobnym MGMT, jeśli jest
włączony. Mapa rozdziela **Management** i grupy NIC, zachowując numery slotów
oraz nazwy kart, również przy lukach, np. NIC 1, 3 i 7. Filtr **Network card**
wybiera konkretną kartę według jej identyfikatora; **Find interface** wyszukuje
również nazwę karty. Filtr karty łączy się z zakresem **Show interfaces**:
wybrana karta i **Management only** mogą dać pusty wynik opisany jako brak
interfejsów pasujących do filtrów. **Show all interfaces** resetuje także kartę NIC.
Kliknięcie portu nadal otwiera wspólny edytor IP, opcjonalnego VLAN-u i **Leads to**.

Istniejące serwery otrzymują nowy widok po odświeżeniu aplikacji. Zmiana widoku
nie wymaga migracji backendu, schematu ani danych; identyfikatory kart, ich nazwy,
adresy IP i pozostałe zapisane przypisania pozostają bez zmian.

## Edycja i ochrona danych

Zmiana prędkości oraz dodanie portów zachowują istniejące przypisania. Zmniejszenie
liczby portów usuwa najwyższe numery. Usunięcie środkowej karty nie zmienia numerów
slotów innych kart. Ponowne dodanie karty w tym samym slocie tworzy nową kartę;
nie przejmuje dawnych przypisań. Zmiana rodziny złączy karty wymienia jej porty.

Jeśli edycja usuwa etykiety, cele, adresy IP lub VLAN-y, **Save device** najpierw wyświetla dokładny
podgląd strat. Dopiero **Confirm removal and save** zatwierdza zmianę. Modyfikacja
formularza unieważnia podgląd. API niezależnie kontroluje wersję i potwierdzenie.
Konflikt równoczesnej edycji zachowuje szkic i wymaga jawnego ponownego wczytania
urządzenia oraz przeglądu zmian. Zwykły zapis bez zmian nie zwiększa wersji.

**Delete device → Confirm delete** usuwa urządzenie i porty, zachowując historię.
Komunikat po usunięciu podaje historyczny identyfikator urządzenia.

## Wyszukiwanie i historia

Lista ma wyszukiwanie nazwy/modelu/opisu, filtry typu i vendora oraz strony po
20 urządzeń. **Device history** pokazuje zapisane zmiany, z danymi przed i po.
Wprowadź identyfikator usuniętego urządzenia, aby zobaczyć jego historię. Konto
aktora jest identyfikowane globalnym numerem konta; brak aktora oznacza tryb otwarty.
Historia jest również stronicowana.

## API i utrzymanie

Prefiks: `/api/device-visualization/devices`. Dostępne są lista, CRUD, podgląd
`POST /{id}/update-preview`, edycja `PUT /{id}/ports/{portId}` i historia
`GET /{id}/audit`. Lista przyjmuje `query`, `deviceType`, `vendor`, `limit` (1–100)
i `offset`; historia `limit`/`offset`. Wybór tenanta używa `X-Tenant-ID`.

Edycja wymaga `expectedVersion`; usuwanie danych portów dodatkowo
`confirmPortDataRemoval: true`, a DELETE `confirmDelete: true` w JSON body.
HTTP 409 z `detail.code` oznacza `stale_version` lub `confirmation_required`.
Błędny kształt danych daje 422, konflikt nazwy 400, brak zasobu 404.

Tworzenie i edycja urządzenia przyjmują opcjonalne pole boolean `managementPort`.
`true` dodaje MGMT (parę dla macierzy), a `false` wyłącza je. Pominięcie pola przy tworzeniu nie dodaje
MGMT; interfejs **New device** wysyła domyślnie `true`. Pominięcie pola przy edycji
zachowuje zapisane ustawienie, także dla starszych klientów API. Port korzysta
z istniejących grup, portów, wersjonowania i audytu; nie wymaga migracji schematu.

Tabele `dv_devices`, `dv_port_groups`, `dv_ports`, `dv_audit` powstają przy starcie
w każdej zarejestrowanej bazie oraz podczas tworzenia tenanta. Dane, wersja i audyt
zmieniają się w jednej transakcji. Nie ma osobnej bazy ani dodatkowego wolumenu.
Backup wszystkich baz tenantów obejmuje też ten moduł; patrz [utrzymanie serwera](maintenance.md).

Aktualizacja limitu SFP dla switchy z 32 do 48 migruje ograniczenie w istniejących
bazach przy starcie backendu, zachowując identyfikatory, przypisania i audyt.
Obsługiwane są m.in. konfiguracje 48 SFP + 6 lub 8 QSFP (łącznie 54 lub 56 portów).

Przy starcie backendu idempotentna migracja rozszerza wcześniejsze ograniczenie
`CHECK` typu urządzenia o `router` i `storage`. Zachowuje identyfikatory urządzeń, grupy,
porty, przypisania, audyt oraz sekwencję identyfikatorów; nie wymaga ręcznej edycji bazy.

Kontrolery korzystają z istniejących grup NIC, bez dodatkowej migracji pól bazy.
Wewnętrzne sloty grup 1–8 oznaczają A, a 9–16 oznaczają B; API zawsze pokazuje
lokalne sloty 1–8 wraz z `controller`. Ten zapis jest szczegółem backendu.

## Adres IP interfejsu i opcjonalny VLAN

Pole **IP address** w edytorze portu przyjmuje IPv4 lub IPv6, opcjonalnie z prefiksem,
np. `192.0.2.10`, `192.0.2.10/24` albo `2001:db8::10/64`. Adres należy do interfejsu:
zapis z prefiksem zachowuje adres hosta, nie zastępuje go adresem sieci. VLAN jest
opcjonalny i niezależny od adresu IP; można zapisać samo IP, sam VLAN lub oba.
Dotyczy to wszystkich portów, także MGMT. Puste pole usuwa adres przy zapisie.
Tabela portów pokazuje kolumnę **IP address** i wyszukuje również po adresie;
podpowiedź oraz dostępna nazwa gniazda na panelu zawierają zapisane IP.

API przypisania i odpowiedź portu zawierają nullable `ipAddress` (do 64 znaków).
Adres jest normalizowany: IPv6 otrzymuje skrócony zapis, a prefiks zapis liczbowy.
Adresy ze strefą `%`, np. `fe80::1%eth0`, są odrzucane. Niepoprawny adres daje 422.
`ipAddress: null` lub pusty ciąg usuwa IP; pominięcie pola podczas edycji zachowuje
dotychczasowy adres dla starszych klientów. Operacje VLAN nie wymagają adresu IP.

Przy starcie backendu idempotentna migracja dodaje kolumnę `ip_address` do
`dv_ports`, zachowując istniejące porty, przypisania i audyt. Dotychczasowe porty
mają początkowo puste IP. Zapis adresu korzysta ze wspólnej wersji i audytu.
Usunięcie portu zawierającego tylko IP również wymaga podglądu strat i potwierdzenia;
`removedConfiguredPortCount` obejmuje porty z IP lub VLAN-em, licząc każdy raz.

W edytorze portu wybierz **Port mode**: **Access** (jeden Access VLAN) albo
**Trunk** (Allowed VLANs: lista `10,20,100-110` lub `all`). Trunk może mieć
opcjonalny Native VLAN. Numery VLAN są z zakresu 1–4094. **Not configured** usuwa
konfigurację VLAN przy zapisie. Zmiana trybu zeruje niepasujące pola formularza.
Zapis jest ręczną dokumentacją, nie wysyła konfiguracji do urządzenia.

Konfiguracja jest dostępna dla portów wszystkich typów urządzeń, zapisywana
z wersją i audytem, zachowana przy zmianie prędkości i zwykłej edycji przypisania.
Usunięcie skonfigurowanego portu wymaga podglądu i potwierdzenia nawet bez etykiety
lub celu. Migracja dodaje pola do istniejących portów bez zmiany ich ID.

API portu przyjmuje także `portMode`, `accessVlan`, `trunkVlans`, `nativeVlan`.
Brak wszystkich czterech pól zachowuje dotychczasową konfigurację dla starszych
klientów; jawne `portMode: null` bez VLAN-ów czyści ją. Lista trunk jest
normalizowana, sortowana i pozbawiana powtórzeń. Native VLAN jest dokumentowany
niezależnie od listy Allowed VLANs.

## Konwencja nazw portów switcha

W **New device / Edit device → Port naming** wybierz:

- `Eth 1 / SFP 1 / QSFP 1` — numeracja osobna dla każdej rodziny (domyślna);
- `1/1/1` — unit / slot / port, z edytowalnymi numerami unit i slot;
- `1/0/1` — unit / 0 / port, z edytowalnym unit;
- `1/1` — unit / port;
- `1, 2, 3` — numeracja ciągła.

Formaty liczbowe numerują porty kolejno: Ethernet, SFP, QSFP. Dlatego nazwy nie
powtarzają się pomiędzy rodzinami. Dodanie portów wcześniejszej rodziny przesuwa
numery kolejnych rodzin. Zmiana dotyczy wyłącznie nazw prezentowanych: identyfikatory,
etykiety, cele i VLAN-y pozostają zachowane. Numer unit: 1–16; slot: 0–16.
Routery, firewalle i karty serwera zachowują nazwy według rodzin lub kart. Istniejące switche
po migracji nadal używają nazw według rodziny. API: `portNaming`, `portUnit`, `portSlot`;
edycja starszym klientem bez tych pól zachowuje zapisaną konwencję.

Panel switcha układa każdą rodzinę portów w dwóch rzędach, parami pionowo:
1 nad 2, 3 nad 4 itd. Liczba kolumn rośnie wraz z liczbą portów; na wąskim
ekranie przewija się sam panel. Układ nie zmienia numeracji ani konfiguracji.
