# Device Visualization

Narzędzie służy do ręcznej dokumentacji fizycznych portów switchy, firewalli
Check Point/FortiGate oraz serwerów. Nie odpyta urządzenia, nie wymaga haseł i nie
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

1. Wybierz **New device**, typ i nazwę; opcjonalnie opis oraz własną nazwę modelu.
2. Switch/firewall: ustaw liczbę portów Ethernet, SFP i QSFP oraz prędkość każdej
   rodziny. Dla firewalla wybierz Check Point, FortiGate lub wariant generyczny.
3. Serwer: dodaj 1–16 kart NIC. Każda karta ma niezależny typ złącza, 1–8 gniazd,
   prędkość i opcjonalną nazwę. **Add network card** zajmuje pierwszy wolny slot.
4. Użyj **Save device**. Wybierz port na panelu, wpisz etykietę i **Leads to**, a
   następnie **Save assignment**. **Clear assignment** usuwa cel i zachowuje
   aktualną etykietę edytora.

Prędkości: Ethernet 1/10G, SFP 10/25G, QSFP 40/100G. Maksymalnie 128 portów na
urządzenie; switch: do 96 Ethernet, 48 SFP i 16 QSFP; firewall: do 96 Ethernet,
32 SFP i 16 QSFP. Wygląd firewalla
jest generyczny; wpisany model nie pobiera specyfikacji producenta. Serwer pokazuje
tylny panel i osobne sloty NIC. Na telefonie panel portów przewija się poziomo.

## Edycja i ochrona danych

Zmiana prędkości oraz dodanie portów zachowują istniejące przypisania. Zmniejszenie
liczby portów usuwa najwyższe numery. Usunięcie środkowej karty nie zmienia numerów
slotów innych kart. Ponowne dodanie karty w tym samym slocie tworzy nową kartę;
nie przejmuje dawnych przypisań. Zmiana rodziny złączy karty wymienia jej porty.

Jeśli edycja usuwa etykiety lub cele, **Save device** najpierw wyświetla dokładny
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

Tabele `dv_devices`, `dv_port_groups`, `dv_ports`, `dv_audit` powstają przy starcie
w każdej zarejestrowanej bazie oraz podczas tworzenia tenanta. Dane, wersja i audyt
zmieniają się w jednej transakcji. Nie ma osobnej bazy ani dodatkowego wolumenu.
Backup wszystkich baz tenantów obejmuje też ten moduł; patrz [utrzymanie serwera](maintenance.md).

Aktualizacja limitu SFP dla switchy z 32 do 48 migruje ograniczenie w istniejących
bazach przy starcie backendu, zachowując identyfikatory, przypisania i audyt.
Obsługiwane są m.in. konfiguracje 48 SFP + 6 lub 8 QSFP (łącznie 54 lub 56 portów).

## Konfiguracja VLAN portu

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
Firewalle i karty serwera zachowują dotychczasowe konwencje. Istniejące switche
po migracji nadal używają nazw według rodziny. API: `portNaming`, `portUnit`, `portSlot`;
edycja starszym klientem bez tych pól zachowuje zapisaną konwencję.

Panel switcha układa każdą rodzinę portów w dwóch rzędach, parami pionowo:
1 nad 2, 3 nad 4 itd. Liczba kolumn rośnie wraz z liczbą portów; na wąskim
ekranie przewija się sam panel. Układ nie zmienia numeracji ani konfiguracji.
