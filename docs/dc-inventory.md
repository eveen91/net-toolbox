# DC Inventory

DC Inventory dokumentuje centra danych, szafy i położenie urządzeń w jednostkach U.
Korzysta z tych samych urządzeń co [Device Visualization](device-visualization.md):
nie tworzy drugiej ewidencji ani kopii portów. Przeniesienie urządzenia zachowuje
jego identyfikator, karty NIC, kontrolery, MGMT, adresy IP, VLAN-y i cele połączeń.

## Uprawnienia i tenanty

Moduł wymaga uprawnienia `dc-inventory`. Istniejącym rolom administrator musi
nadać je jawnie; administratorzy z `*` mają dostęp automatycznie. Uprawnienie
`device-visualization` samo w sobie nie pozwala zarządzać centrami danych i szafami.
Udostępnia jednak katalog lokalizacji tylko do odczytu pod API Device Visualization,
aby wybierać położenie własnych urządzeń. DC Inventory pozwala przypisywać istniejące
urządzenia; ich porty i konfigurację edytuje się w Device Visualization.

Dane, lokalizacje i audyt należą do aktywnego tenanta. API używa `X-Tenant-ID`;
identyfikatory szaf i urządzeń z innych tenantów nie tworzą wspólnego katalogu.

## Centra danych, szafy i urządzenia

1. Utwórz centrum danych, a następnie szafę o pojemności 1–100U.
2. W **Unassigned** wybierz istniejące urządzenie i **Assign to rack**.
3. Podaj wysokość urządzenia, centrum danych, szafę i **Starting U (bottom)**.
   Zatwierdź przez **Save placement**.
4. Widok szafy pokazuje zajęte i wolne U. Wybór urządzenia lub **Move / unassign**
   otwiera edytor położenia; wybranie braku szafy usuwa przypisanie.

U1 znajduje się na dole. Początek zakresu jest włączony: urządzenie 2U od U3
zajmuje U3–U4, a jego najwyższe U wynosi `rackPosition + heightU - 1`.
Wysokość urządzenia jest liczbą całkowitą 1–100U. Centrum danych wynika z wybranej
szafy; sam wybór centrum bez szafy nie zapisuje niezależnego przypisania DC.
Szafa pozostaje w centrum danych wybranym przy jej tworzeniu.

Dotychczasowe urządzenia są początkowo nieprzypisane i mają nieznaną wysokość,
pokazywaną jako **Not recorded**. Interfejs wymaga wysokości przy zapisie formularza
urządzenia lub położenia; nie należy traktować wartości początkowej edytora jako
wcześniej zapisanej wysokości. Dane portów pozostają bez zmian.

Nazwy centrów są unikalne w tenancie, a nazwy szaf w obrębie centrum, bez
rozróżniania wielkości liter. **Unassigned** wyszukuje urządzenia i pokazuje
25 pozycji na stronie. **History** udostępnia historię zmian z danymi przed i po.

## Panele porządkowania kabli

Wybierz szafę i **Add cable management panel (1U)**. Podaj nazwę oraz początkowe U;
domyślna nazwa zawiera szafę i pozycję. Rackmount Cable Management Panel jest
pasywnym elementem wspólnej ewidencji, zawsze zajmuje 1U i nie ma portów sieciowych
ani MGMT. Jest widoczny w Rack elevation i Device Visualization. Przenosi się go
przez ten sam edytor położenia; edycja nazwy i usuwanie są w Device Visualization.
Obowiązują wspólne reguły zajętości szafy i historia zmian.

`POST /api/dc-inventory/cable-panels` wymaga `dc-inventory` oraz pól `name`,
`rackId`, `rackPosition` (opcjonalnie `description`). Typ i wysokość ustala serwer.
Nie trzeba nadawać uprawnienia Device Visualization do samego dodania panelu.
Nazwy są unikalne we wspólnej ewidencji urządzeń tenanta.

## Ochrona danych

Zapis odrzuca nakładające się zakresy U oraz urządzenia wystające poza pojemność
szafy. Nie można zmniejszyć szafy poniżej najwyższego zajętego U. Przed usunięciem
szafy trzeba przenieść lub odpiąć wszystkie urządzenia; przed usunięciem centrum
trzeba usunąć jego szafy. Usunięcie pustej lokalizacji wymaga potwierdzenia.

Aktualizacja i usuwanie porównują `expectedVersion` z bieżącą wersją. Po konflikcie
należy ponownie wczytać dane i przejrzeć położenie. Przypisanie współdzieli wersję
urządzenia z Device Visualization, więc równoczesna edycja portu może unieważnić
wcześniej otwarty formularz położenia. Zapis, wersja i audyt są atomowe; zmiana
położenia z DC Inventory trafia do historii urządzenia oraz historii inwentarza.
Zapis bez zmian nie zwiększa wersji. Ochrona zakresów działa również w bazie danych.

## API

Prefiks: `/api/dc-inventory`.

| Metoda i ścieżka | Zastosowanie |
| --- | --- |
| `GET /datacenters`, `POST /datacenters` | Katalog i utworzenie centrum |
| `PUT /datacenters/{id}`, `DELETE /datacenters/{id}` | Edycja lub usunięcie centrum |
| `GET /racks`, `POST /racks` | Katalog i utworzenie szafy |
| `GET /racks/{id}`, `PUT /racks/{id}`, `DELETE /racks/{id}` | Zawartość, edycja lub usunięcie szafy |
| `GET /devices` | Wspólne urządzenia; filtry `unassigned`, `rackId`, `query` |
| `PUT /devices/{id}/placement` | Położenie istniejącego urządzenia |
| `GET /audit` | Historia inwentarza |

Listy używają `limit` (1–100) i `offset`; `/racks` przyjmuje też `dataCenterId`.
Centrum przyjmuje `name` i opcjonalne `description`; nowa szafa dodatkowo
`dataCenterId` i `heightU`. Edycja wymaga `expectedVersion`; DELETE również
`confirmDelete: true` w JSON body. Położenie przyjmuje `expectedVersion`,
`rackId`, `rackPosition`, `heightU`. Pominięte pola położenia zachowują wartości;
`rackId: null` odpina urządzenie i usuwa początkowe U. Przypisanie do szafy wymaga
wysokości oraz początkowego U. API zachowuje zgodność ze starszymi klientami,
które nie podają pól lokalizacji w Device Visualization.

HTTP 409 obejmuje `stale_version`, `placement_conflict`, `rack_too_small`,
`location_not_empty` i `confirmation_required` w `detail.code`. Nieprawidłowa
operacja daje 400, niepoprawny kształt danych 422, brak zasobu 404, a niedostępna
lub zajęta baza 503. Katalog tylko do odczytu dla Device Visualization jest pod
`GET /api/device-visualization/inventory/datacenters` oraz
`GET /api/device-visualization/inventory/racks`.

## Aktualizacja i utrzymanie

Restart backendu automatycznie i idempotentnie aktualizuje istniejące bazy tenantów:
tworzy tabele `dc_datacenters`, `dc_racks`, `dc_audit`, pola lokalizacji w
`dv_devices` oraz ochronę zakresów U. Nowe tenanty otrzymują ten sam schemat.
Nie są potrzebne nowe zależności, osobna baza ani wolumen. Kopie baz tenantów
obejmują inwentarz i wspólne urządzenia; patrz [utrzymanie serwera](maintenance.md).
