# Nowe GUI net::toolbox — propozycja do przeglądu

Status: projekt, nie wdrożenie. Data: 2026-10-13. Makiety używają wyłącznie przykładowych danych, nie przedstawiają stanu infrastruktury. Nie zmieniono aplikacji ani istniejących zmian roboczych.

Aktualizacja: wariant B został następnie wdrożony. [Zakres implementacji i weryfikacja](IMPLEMENTATION.md); bieżące tokeny i komponenty opisuje [DESIGN.md](../../DESIGN.md). Poniższy dokument zachowuje pierwotną propozycję i audyt.

## Cel i zakres

Przekształcić zbiór osobnych narzędzi w spójne środowisko pracy administratora sieci. Najważniejszy rezultat: użytkownik zawsze wie, gdzie szukać obiektu, gdzie są jego dane, gdzie go edytować i jaki zakres obejmuje operacja. Priorytety potwierdzone przez użytkownika: przypadkowe rozmieszczenie przycisków i danych w IPAM, niemieszcząca się wizualizacja urządzenia, różne szerokości kolumn Interfaces/Routes i niespójność całej aplikacji.

Zakres audytu obejmuje powłokę aplikacji, wszystkie osiem modułów z rejestru, ekran startowy, konto, logowanie, administrację i tenanty. Wnioski pochodzą z aktualnego kodu JSX/CSS, dokumentacji produktu i tenantów oraz zapytania graphify. Nie wykonano audytu działającej aplikacji w przeglądarce; obserwacje geometrii wyliczono z CSS. Dostępność, zachowanie przy powiększeniu i rzeczywiste dane wymagają sprawdzenia przy wdrożeniu. Makiety SVG są propozycjami kompozycji, nie interaktywnym prototypem.

## Makiety

Alternatywa z nawigacją u góry, odzyskująca 216 px szerokości: [wariant B — projekt i porównanie](TOP-NAVIGATION.md).

- [IPAM: lista podsieci, tabela adresów i inspektor](ipam.svg).
- [Device Visualization: cały panel urządzenia i inspektor portu](devices.svg).
- [Routing Map: wspólne granice kolumn Interfaces i Routes](routing.svg).

Każda makieta ma 1440 × 900 px i pokazuje ten sam system: nawigacja, tenant, nagłówek, lokalne widoki, obszar danych. Angielski pozostaje językiem interfejsu, zgodnie z obecną aplikacją. Dokumentacja projektu jest po polsku. Wdrożenie nie powinno mieszać obu języków w jednym ekranie.

## Audyt: problem → konsekwencja → rozwiązanie

| Priorytet | Dowód w repozytorium | Problem i konsekwencja | Decyzja projektowa |
|---|---|---|---|
| P0 | `src/tools/post-change-validation/ExecutionTab.jsx`, `DiffViewTab.jsx`, `PirReportTab.jsx` | Execution używa SAMPLE_TESTS i timera; Diff pokazuje stały pozytywny wynik; PIR zmienia lokalny stan i deklaruje eksport. GUI może wyglądać jak dowód wykonanych testów. | Widoczny tryb Demonstration. Realne statusy dopiero z dowodów backendu; brak danych nie oznacza PASS. |
| P1 | `src/components/Toolbar.jsx`, `src/index.css`, `src/tenants/tenants.css` | Wszystkie moduły, konfiguracja, konto i tenant konkurują o poziomy pasek. `.nt-toolbar` ma przewijanie w osi X. | Stały panel nawigacji z grupami; górny pasek służy kontekstowi i kontu. |
| P1 | `src/App.jsx` | Nawigacja to lokalny `useState("home")`; wybór obiektu i widoku nie jest adresem strony. | Adresowalne widoki, Back/Forward i odtwarzanie widoku po odświeżeniu. |
| P1 | `src/index.css`, `.nt-main` | Limit 1280 px i padding 28 px pozostawiają na dużym ekranie niewykorzystaną szerokość. | Moduły danych wykorzystują całą dostępną szerokość. Limit szerokości pozostaje dla tekstu i prostych formularzy. |
| P1 | `src/tools/ipam/Ipam.jsx`, `IpamToolbar.jsx` | Start to search, bez listy podsieci; przełączniki widoków, narzędzia planowania, import i ustawienia stoją obok wyszukiwania. | Domyślnie lista podsieci; osobno nawigacja lokalna, filtry i akcje. |
| P1 | `src/tools/ipam/SubnetDetail.jsx` | Inventory łączy statystyki, podsieci, heatmapę/tabelę, DHCP, rezerwacje i tagi. Otwarcie rekordu z tabeli ustawia `inventoryView("heatmap")`. | Podsieć ma zakładki tematyczne; tabela i mapa otwierają ten sam inspektor bez zmiany widoku. |
| P1 | `src/tools/device-visualization/device-visualization.css`, `DeviceFaceplate.jsx` | Stała szerokość portów i layout `max-content` wymuszają poziomy scroll. Dla 48 Ethernet przy numeracji liczbowej: 24 × 82 + 23 × 8 = 2152 px, jeszcze przed SFP/QSFP. | Widok Fit, tryb powiększenia i alternatywna tabela. Czytelne dane nie są pomniejszane wraz z rysunkiem. |
| P1 | `src/tools/device-visualization/DeviceVisualization.jsx` | Lista zajmuje 270 px, edytor jest pod panelem urządzenia; po wyborze portu trzeba szukać formularza niżej. | Port otwiera inspektor obok panelu. Lista urządzeń znika z obszaru roboczego na mniejszych ekranach. |
| P1 | `src/tools/routing-map/RoutingTable.jsx`, `src/tools/shared.css` | Dwie trzykolumnowe tabele bez kontraktu szerokości i `colgroup`; auto layout zależy od zawartości i elementów edycyjnych. | Wspólny preset kolumn i paddingów. Edycja nie zmienia szerokości kolumn. |
| P1 | `src/pages/HomePage.jsx` | Karty to klikalne `div`; opis deklaruje, że wszystko działa lokalnie w przeglądarce, choć moduły korzystają z serwera. | Linki dostępne z klawiatury; opis zgodny z self-hosted architekturą i zakresem każdego narzędzia. |
| P2 | `src/index.css`, `src/tools/shared.css` | Wiele etykiet ma 10–11 px, monospace obejmuje nazwy i treści nietechniczne; input usuwa outline. | Sans do interfejsu, mono do adresów i nazw portów. Wspólny, widoczny focus. |
| P2 | `src/tools/shared.css`, CSS modułów | Tabele domyślnie mają max-height 360 px, część modułów nadpisuje limit; osobne systemy przycisków i zakładek. | Jeden zestaw komponentów i zasad przewijania; lokalne wyjątki tylko dla rzeczywistych potrzeb danych. |
| P2 | `src/tools/post-change-validation/PostChangeValidation.jsx`, `src/tools/routing-map/RoutingMap.jsx`, `src/tools/troubleshoot/Troubleshoot.jsx` | Różne konstrukcje zakładek; walidacja ma klikalne `div`. | Nawigacja trasami jako linki; zakładki wewnątrz obiektu z pełną obsługą klawiatury. |

Zachowujemy już dobre rozwiązania: serwerową paginację adresów, wyszukiwanie z debounce, kontrolę wersji rekordów, podgląd przenosin, istniejące zabezpieczenia niezapisanych zmian, audyt oraz rozdzielenie uprawnień IPAM. Redesign nie powinien ich zastępować uproszczoną makietą.

## Architektura informacji

```text
net::toolbox
├─ Workspace
├─ Infrastructure
│  ├─ IPAM
│  ├─ Device Visualization
│  └─ Routing Map
├─ Diagnostics
│  ├─ Troubleshoot
│  ├─ Connection Test
│  └─ Post-Change Validation
├─ Utilities
│  ├─ IP Calculator
│  └─ Subnet Splitter
└─ Administration [według uprawnień]
   ├─ Tenant access
   ├─ Users [administracja platformy]
   ├─ Roles [administracja platformy]
   ├─ Active Directory [administracja platformy]
   └─ Audit [właściwy zakres]
```

Tenant jest granicą danych, nie filtrem. Jest stale widoczny w górnym pasku, również na ekranie telefonu. Globalne kalkulatory mają podpis `Browser utility · Global`, moduły bazodanowe nazwę aktywnego tenanta. Zmiana tenanta najpierw rozwiązuje niezapisany formularz, potem weryfikuje dostęp, odmontowuje moduł i czyści selekcję, cache oraz strumienie. Nie odtwarza numeru obiektu z poprzedniego tenanta. W razie błędu nie pokazuje danych pod nową nazwą tenanta. Zachować obecne zasady osobnego wyboru w kartach przeglądarki.

Nie utożsamiać `tenant-admin` z administratorem platformy. Widoczność ekranów i akcji wynika z istniejących uprawnień, a serwer pozostaje źródłem autoryzacji. Brak dostępu do modułu ukrywa jego link; tryb tylko do odczytu zachowuje dane i pokazuje `Read only`, bez akcji zapisu. Nie zastępować indywidualnych `ipam.read/write/scan/admin` jednym ogólnym przełącznikiem.

## Wspólna anatomia ekranu

1. Panel boczny: logo, Workspace, pogrupowane moduły, administracja na dole. Aktywny moduł ma stonowane tło, nie jaskrawy wypełniony przycisk.
2. Pasek kontekstu: tenant i konto. Wyszukiwarka na początek obejmuje nawigację i bieżący moduł; wyszukiwanie między modułami wymaga osobnej pracy backendowej i nie jest obiecywane.
3. Nagłówek strony: tytuł, krótki opis, jedna główna akcja po prawej. Operacje rzadkie w `More`; destrukcyjne na końcu menu.
4. Nawigacja lokalna: podstrony modułu zawsze pod nagłówkiem. Nie mieszać jej z filtrami.
5. Obszar roboczy: lista/selector po lewej, dane w środku, inspektor po wyborze po prawej. Proste kalkulatory używają układu formularz → wynik bez dodatkowych paneli.
6. Pasek narzędzi danych: wyszukiwanie, filtry, liczba wyników, przełącznik widoku. Akcje zbiorcze pojawiają się dopiero po zaznaczeniu.
7. Stopka tabeli: zakres wyników i paginacja. Zapis formularza jest w stałej stopce inspektora.

Jedno znaczenie dla każdego regionu. Dodawanie podsieci nie ląduje w filtrach; ustawienia nie pojawiają się wśród wyników; usuwanie nie konkuruje wizualnie z edycją. Nie tworzymy jednego ogromnego komponentu wymagającego kilkudziesięciu flag — wspólna anatomia dopuszcza listę, tabelę, canvas i formularz.

## IPAM

### Struktura

Nawigacja modułu: `Subnets`, `Overview`, `Planning`, `Data quality`, `Archive`. `Import` to akcja listy uruchamiająca pełny proces: plik → podgląd → wynik. `Planning` zawiera Allocator i Resubnet z zachowaniem obecnych podglądów. Ustawienia i zarządzanie tagami dostępne z menu modułu według uprawnień.

Domyślny ekran Subnets pokazuje listę dostępnych sieci: CIDR, opis, VLAN, tagi i skrócone wykorzystanie. Drzewo opiera się na istniejącym `parentId`; nie sugeruje, że wszystkie nakładające się CIDR tworzą potwierdzoną hierarchię. Nad listą wyszukiwanie i filtry. Brak wybranego obiektu oznacza przegląd listy, a nie instrukcję „wyszukaj coś”.

Po wyborze podsieci: breadcrumb rodziców, CIDR, opis i VLAN, podsumowanie stanów, następnie zakładki `Addresses`, `DHCP & ranges`, `Child subnets`, `History`, `Settings`. Przydzielanie adresu jest akcją Addresses, skanowanie akcją podsieci z osobnym potwierdzeniem zakresu, eksport w menu danych. Przeniesienie do tenanta i archiwizacja mają przegląd wpływu.

### Adresy

Tabela jest domyślnym widokiem pracy; mapa to alternatywna analiza zajętości. Tabela pokazuje zapisane rekordy, z jednoznacznym podpisem. Heatmapa obejmuje przestrzeń adresową, stronicowaną dla dużych sieci; niezapisane adresy nie są automatycznie wolne. Zachować osobno: Used, Reserved, Free (recorded), Not recorded. Nie sumować rodzica i dzieci jak niezależnych zakresów i nie prezentować zajętości jako dostępności hosta.

Wiersz adresu i komórka mapy otwierają ten sam inspektor. W tabeli nie następuje przełączenie do mapy. Inspektor: adres i stan, hostname/opis, zespół/środowisko/typ, tagi, blokada i dostępne wykluczenia, historia. Formularz ma ręczny zapis; zmiana statusu nie zapisuje niespodziewanie wszystkich pozostałych pól. Pola i akcje muszą respektować obecne uprawnienia.

Zaznaczenie zbiorcze zachowuje obecną semantykę: tylko bieżąca filtrowana strona. Podpis `12 selected on this page`; nie sugerować zaznaczenia całej bazy. Zmiana filtrów/paginacji czyści zaznaczenie jawnie. Wynik operacji podaje sukcesy, pominięcia i powody, bez fałszywego komunikatu o pełnym sukcesie.

### Przebieg

Lista podsieci → wybór → tabela adresów → otwarcie adresu → edycja w inspektorze → zapis → aktualizacja wiersza bez utraty filtrów i scrolla. Konflikt wersji zachowuje draft, pokazuje aktualną wersję i oferuje ponowne sprawdzenie; nie nadpisuje cudzych zmian.

## Device Visualization

Lista urządzeń: nazwa, typ, model i liczba przypisanych portów. Filtry pozostają zgodne z API: vendor ma zastosowanie do firewalli; nie dodawać fikcyjnych lokalizacji, racków lub producentów switchy. Nagłówek obiektu: nazwa, opis, model, podsumowanie portów. Widoki: `Panel`, `Port table`, `History`; edycja urządzenia jest akcją, nie kolejnym niezwiązanym ekranem.

### Cały panel w ekranie

Canvas jest ograniczony do dostępnego obszaru ekranu. Początkowo `Fit`: cała geometria grup portów mieści się w szerokości canvasu. Obliczenie skali z rzeczywistego bounding box i ResizeObserver, z marginesem; canvas nie zwiększa szerokości strony. Po otwarciu inspektora przelicza się Fit, jeśli użytkownik nie wybrał ręcznego zoomu. Kontrolki: `Fit`, minus, aktualna skala, plus, `Fullscreen`. Powiększony widok może przewijać wyłącznie canvas. Fullscreen ma widoczne wyjście i obsługę Escape.

Nie pomniejszać całego JSX z tekstem i przyciskami do nieczytelnego rozmiaru. Widok Fit pokazuje schemat portów: rodzinę, numer i przypisanie; pełne nazwy, etykiety, cel i VLAN znajdują się w inspektorze i tabeli. Utrzymać fizyczny porządek par 1/2, 3/4 itd., osobne grupy Ethernet/SFP/QSFP i NIC. Nie łamać portów do przypadkowych rzędów tylko po to, by pasowały do szerokości.

Jeśli Fit sprowadza cele interakcji poniżej przyjętego minimum, schemat służy do orientacji, a wybór zapewnia czytelna lista/tabela i wyszukanie portu. Nie nakładać na siebie powiększonych hitboxów. Na małym ekranie domyślnie tabela; Panel i Fullscreen dostępne świadomie. Obsługa klawiatury: wejście jednym Tab do schematu, strzałki między portami, Enter wybiera, focus ma czytelną nazwę. Zaznaczenie jest wspólne dla panelu i tabeli.

### Edycja

Wybrany port otwiera inspektor obok canvasu: pełna nazwa, rodzina/prędkość, etykieta, Leads to, tryb Access/Trunk i odpowiednie VLAN-y. Zapis w stałej stopce; pole niezapisanych zmian widoczne. Zmiana portu, urządzenia, modułu lub tenanta ma wspólne rozstrzygnięcie `Save / Discard / Stay`. Operacji asynchronicznej nie można zapisać do nowo wybranego obiektu.

Przypisanie dokumentacyjne nie jest statusem linku. Widoczny podpis `Saved documentation · No live link status`. Leads to pozostaje tekstem; nie rysujemy potwierdzonych połączeń do innych urządzeń bez relacji w danych. Zmiana VLAN nie konfiguruje sprzętu. Redukcja liczby portów pokazuje istniejący podgląd utraconych przypisań/konfiguracji i wymaga potwierdzenia. Historia usuniętych urządzeń pozostaje dostępna przez wyszukanie ID.

## Routing Map — wyrównanie kolumn

Najpierw lista zapisanych hostów, potem szczegóły hosta. Edytor importu przenosimy do osobnego procesu `Import routes`; nie zajmuje stale lewej strony ekranu operacyjnego. Lokalna nawigacja: `Hosts`, `Routing test`, `Topology`.

W szczegółach hosta sekcje Interfaces i Routes zajmują identyczną szerokość i zaczynają się w tej samej osi. Przy szerokim widoku wspólny trzykolumnowy preset: pierwsza 220 px, druga 240 px, trzecia reszta. Dla 960 px danych granice to 0 / 220 / 460 / 960 px. Obie tabele mają jawny `colgroup`, `table-layout: fixed`, identyczny padding 12 px oraz wiersze co najmniej 40 px. W edycji input mieści się we własnej komórce i nie przelicza kolumn. Makieta pokazuje tabelę tego samego hosta, nie porównuje różnych obiektów.

| Slot | Interfaces | Routes | Zasada |
|---|---|---|---|
| A: 220 px | Name | Network | Pełna wartość techniczna dostępna do kopiowania |
| B: 240 px | Address | Next hop | Monospace; wsparcie długich adresów bez zmiany geometrii |
| C: pozostała przestrzeń | Description | Interface | Opis może zawijać się; nazwa interfejsu ma podgląd pełnej wartości |

Na węższym obszarze wspólny wariant 28% / 30% / 42%, z dolną granicą czytelnej szerokości tabeli. Poniżej niej obie sekcje przechodzą do widoku rekordów label/value, zamiast rozpychać całą stronę. Nie narzucamy takich samych szerokości każdej tabeli w projekcie — wspólny kontrakt stosujemy do zestawionych sekcji o porównywalnej strukturze.

Topology ma Fit, zoom i inspektor hosta dostępny przez kliknięcie i klawiaturę, zamiast danych wyłącznie na hover. Krawędź nadal oznacza współdzieloną sieć z zapisanych danych; nie przedstawia fizycznego kabla ani sprawdzonej ścieżki routingu.

## Pozostałe powierzchnie

| Powierzchnia | Nowy układ i podstawowy przepływ |
|---|---|
| Workspace | Kompaktowy katalog grup narzędzi i lokalnie zapamiętane ostatnie moduły. Krótkie, prawdziwe opisy. Bez zbiorczych wskaźników „zdrowia sieci”, których aplikacja nie zbiera. |
| Connection Test | Konfiguracja po lewej, wyniki po prawej. Źródła → cele → porty → właściwe dla systemu poświadczenia → opcje zaawansowane. Przed startem podsumowanie zakresu. Wyniki rozróżniają brak łączności, błąd wykonania i brak wyniku; filtry stanu i pełne szczegóły. Zachować walidację, limity i parametry SSH/WinRM. Nie obiecywać anulowania zadania bez API. |
| Troubleshoot | Zachować zakres Diagnostics, Locate & Port, Reachability & Route, STP, Inventory, Activity. Ujednolicić nawigację i układ cel → parametry → wynik. Locate ma stały kontekst celu, pod nim czytelne sekcje port health, cable, optics, access. Karty wyników nie zmieniają rozmiaru losowo i pokazują czas oraz źródło. Zachować współdzielony `locateForm` oraz zależność Route check od poświadczeń Locate; nie udawać globalnego kontekstu, którego dziś nie ma. |
| Post-Change Validation | Sekwencja Baseline → Execution → Diff → PIR ze wskazaniem planu i dowodów. Etapy bez danych mają stan Not available, nie sukces. Obecne symulacje wyraźnie Demonstration. Realny run, trwały sign-off i eksport wymagają osobnej integracji; samo GUI nie naprawi ich braku. |
| IP Calculator | Krótki formularz, wynik obok, kopiowanie IP/CIDR/maski, binarny podział jako sekcja rozwijana. Etykiety powiązane z inputami, jasna informacja o prefiksie z pola IP. |
| Subnet Splitter | Sieć i wykluczenia jako wejście, podgląd zakresu i bloki CIDR jako wynik. Błąd wskazuje konkretną linię. Sprawdzanie pojedynczych IP jest wtórną sekcją; zachować istniejące reguły obliczeń. |
| Login / account | Jeden system pól i błędów, obsługa managera haseł. Konto i zmiana hasła w osobnym panelu z właściwym focus. Wygaśnięcie sesji blokuje akcje; nie przechowujemy poświadczeń diagnostyki w localStorage ani URL. |
| Administration / tenants | Oddzielić zakres platformy i aktywnego tenanta. Users/Roles: tabela i inspektor, uprawnienia pogrupowane według modułów. AD: formularz sekcjami zgodny z istniejącymi opcjami. Audit: filtry, tabela, szczegóły zdarzenia; nie sugerować zunifikowanego audytu wszystkich modułów bez agregacji API. |

## System wizualny — proponowane tokeny

To kandydat systemu, nie zatwierdzony globalny DESIGN.md. Styl: płaskie, spokojne powierzchnie, subtelne separatory, czytelna typografia i jeden morski akcent. Bez gradientów tła, dekoracyjnego szkła, nadmiaru pillów i kart w kartach. Tożsamość pozostaje w `net::toolbox`, akcencie i precyzji danych.

| Token | Ciemny wariant | Jasny wariant |
|---|---|---|
| canvas | #11161D | #F3F5F7 |
| surface | #181F28 | #FFFFFF |
| surface-subtle | #202A35 | #EAF0F3 |
| border | #344252 | #CCD5DF |
| text | #E8EDF3 | #17212D |
| text-muted | #A5B2C2 | #536273 |
| primary background | #72D6C3 | #087565 |
| primary text | #10231F | #FFFFFF |
| selection background | #203D3A | #DCF2EC |
| focus ring | #8DE6D5 | #087565 |
| success text | #89DCAC | #17663A |
| warning text | #F1C277 | #835000 |
| danger text | #FFADB4 | #AD2334 |

Tekst i przyciski: Inter self-hosted lub systemowy sans jako fallback. Mono: IBM Plex Mono self-hosted, tylko IP/CIDR/MAC/nazwy portów/CLI. Bez obowiązkowego pobierania fontów z Google w instalacji self-hosted. Typografia: tytuł strony 24/32 px semibold, tytuł obiektu 20/28, treść 14/20, dane 13/20, etykiety minimum 12/16. Liczby tabelaryczne. Body 14 px nie dotyczy mobile inputów: tam co najmniej 16 px.

Skala odstępów: 4, 8, 12, 16, 24, 32 px. Padding obszaru roboczego 24 px desktop, 16 px tablet, 12 px telefon. Kontrolki 36 px desktop, minimum 44 px na dotyku. Wiersze tabeli 40 px standard, opcjonalne 32 px compact tylko desktop. Radius 6 px kontrolki, 8 px powierzchnie. Jeden system ikon SVG 18–20 px z tą samą grubością kreski; bez mieszanki Unicode i emoji.

Stany: hover, focus, selected, disabled, pending, error, success. Akcent oznacza akcję lub wybór; zielony status nie powinien wyglądać jak zaznaczony wiersz. Status zawsze tekst + symbol, nie sam kolor. Ruch wyłącznie jako feedback, 150–200 ms; reduced-motion wyłącza przejścia. Zero animowanych wejść całej strony.

## Responsywność i geometria

| Szerokość viewportu | Kompozycja |
|---|---|
| ≥1600 px | Sidebar 216 px, lista 256–280 px, dane elastyczne, inspektor 320–360 px. Nie wszystkie regiony muszą być zawsze otwarte. |
| 1280–1599 px | Sidebar 200–216 px. Przy otwartym inspektorze zwija się lista obiektów; canvas i tabela zachowują użyteczną szerokość. Makiety 1440 px celowo pokazują ten wariant. |
| 900–1279 px | Nawigacja w wysuwanym panelu z nazwami; lista i szczegół jako dwa widoki. Inspektor zastępuje szczegół lub otwiera pełny panel z kontrolą focus. |
| <900 px | Jeden główny widok: lista → obiekt → inspektor, z jawnym Back. Tenant pozostaje widoczny. Device domyślnie tabela. |
| Telefon / 320 CSS px | Rekordy label/value i przewijanie pionowe. Canvas lub rzeczywiście dwuwymiarowa tabela mogą mieć własny scroll, ale nie cała strona. Pełnoekranowe formularze i kontrolki dotykowe. |

Nie oceniać układu tylko po viewport: pojawienie się inspektora zmniejsza szerokość zawartości. Stosować również container queries. Nie wciskać czterech kolumn na laptop 1366 × 768. Na takim ekranie nagłówek jest kompaktowy, lista zwinięta podczas edycji, a wybrany port i przycisk Save pozostają widoczne bez przewijania całej strony. Tabele mają sticky header; zagnieżdżony scroll stosować świadomie, nie przez globalny limit 360 px.

## Stany i dostępność

| Sytuacja | Zachowanie |
|---|---|
| Pierwsze użycie | Co przechowuje moduł i właściwa akcja Add/Import; dla read-only informacja o potrzebnym dostępie. |
| Brak wyników filtrów | Zachowane filtry, liczba 0, akcja Clear filters. Nie mylić z pustą bazą. |
| Loading | Skeleton stabilnej geometrii; podczas odświeżania stare dane oznaczone jako odświeżane, bez możliwości operacji na nieaktualnej selekcji. |
| Błąd danych | Komunikat przy danym regionie i Retry; nie kasować draftu. Nie pokazywać 0 zamiast nieznanych danych. |
| Skan / zadanie | Zakres, stan z backendu, postęp tylko gdy znany, wynik i błędy. Zmiana widoku nie oznacza anulowania pracy serwera. |
| Konflikt wersji | Zachowany draft, wyjaśnienie, odczyt aktualnej wersji i ponowny podgląd przed zapisem. |
| Archiwizacja / usuwanie | Dokładny obiekt, zakres skutków, wymagany powód jeśli API go wymaga; potwierdzenie w dedykowanym dialogu lub etapie przeglądu. |
| Niepełny sukces | Lista pominiętych elementów i przyczyn; stan warning, nie zbiorczy success. |
| Niezapisane zmiany | Save / Discard / Stay, także przy zmianie tenanta; bez automatycznego nadpisywania. |
| Sesja wygasła | Blokada akcji, ponowne logowanie; sekrety nie są utrwalane. Przywrócenie draftu tylko przy tym samym koncie i tenantcie po weryfikacji dostępu. |

Cel wdrożenia: WCAG 2.2 AA. Kontrast tekstu min. 4.5:1, dużego tekstu 3:1, istotnych granic i wskaźników focus 3:1. Minimum celu interakcji AA to 24 × 24 CSS px z wyjątkami standardu; 44 px przyjmujemy jako własny standard dotyku. Klawiatura obsługuje wszystkie akcje, focus nie jest zasłaniany przez sticky paski, zamknięcie panelu oddaje go elementowi otwierającemu. Dialog ma nazwę, kontrolę focus i Escape; zakładki roving tabindex i strzałki. Linki do stron nie udają zakładek ARIA. Tabele zachowują semantykę i sortowanie `aria-sort`; mapa ma równoważny widok tabelaryczny. Komunikaty async w `aria-live`, błędy powiązane z polami. Sprawdzić zoom 200%, reflow przy 320 CSS px i obsługę managera haseł. Źródło: [W3C WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/).

## Wdrożenie etapami

1. **Wspólna powłoka i komponenty.** AppShell, Sidebar, TenantSwitcher, PageHeader, lokalna nawigacja, Button, Field, StatusBadge, DataTable, Inspector, dialog, Empty/Error/Loading. Dodać adresowalne widoki; dla instalacji self-hosted rozważyć hash routing bez konieczności nowych rewrite serwera. Zachować bramki auth i tenant remount. Nie zmieniać API w ramach kosmetyki.
2. **Routing Map jako pierwszy test tabel.** Jawne kolumny Interfaces/Routes, zgodne wyrównanie, stabilna edycja. Mały zakres pozwala potwierdzić wspólne komponenty przed przebudową IPAM.
3. **Device Visualization.** Fit i zoom, tabela portów, inspektor, responsywne zwijanie listy, focus i kontrola draftu. Zachować wersjonowanie i podglądy zmian struktury urządzenia.
4. **IPAM.** Lista podsieci, hierarchia lokalnych widoków, zakładki podsieci, wspólny inspektor adresu. Dopiero potem ujednolicić import, planowanie, jakość i archiwum. Nie przepisywać jednocześnie hooków skanowania i całego backendu.
5. **Diagnostyka, kalkulatory i administracja.** Przenieść istniejące zachowania do wspólnych komponentów. Oznaczyć demonstracyjne ekrany walidacji przed dalszym rozwojem. Podłączenie rzeczywistych runów/sign-off/eksportu to odrębne zadanie funkcjonalne.
6. **Walidacja przekrojowa.** Oba motywy, klawiatura, laptop/tablet/telefon, różne role, duże dane i konflikt wersji. Usunąć stare globalne klasy `.tabs`, `.tab`, hardcoded kolory i powielone komponenty dopiero po migracji wszystkich konsumentów.

Adresy widoków powinny kodować moduł, ID obiektu, lokalną sekcję oraz jawne filtry. Zakres cache zawsze tenant + moduł + obiekt. ID w URL nie jest dowodem uprawnienia. Nie przechowywać haseł, sekretów ani surowych wyników diagnostyki w URL lub trwałym storage. Ustawienia wyglądu mogą być lokalne, preferencje widoku również po odpowiednim rozdzieleniu zakresu.

## Kryteria odbioru

- IPAM po otwarciu ma widoczną listę podsieci; otwarcie adresu z tabeli nie przenosi do mapy. Filtry i pozycja tabeli pozostają po zapisie.
- Wszystkie moduły mają ten sam układ nagłówka, nawigacji, filtrów i głównych akcji, a nie identyczne bezmyślnie narzucone kontenery.
- Device na 1366 × 768 pokazuje w Fit cały panel 48 Ethernet + grupy uplinków. Dodatkowo sprawdzić 48 SFP + 8 QSFP, firewall i serwer wielo-NIC. Nieczytelny Fit ma dostępny wybór portu z tabeli; zapis i pełna nazwa portu pozostają czytelne.
- Interfaces i Routes mają dokładnie wspólne granice kolumn przy tych samych szerokościach, także w trakcie edycji i z długimi danymi. Testować pustą sekcję, długą nazwę interfejsu i wielowierszowy opis.
- Zmiana tenanta z otwartym formularzem nie gubi zmian bez decyzji, nie pokazuje danych starego tenanta pod nową nazwą i nie utrwala poświadczeń.
- Tryby IPAM read/write/scan/admin i tenant-admin/platform-admin zachowują granice obecnego backendu; bez dostępu nie ma bocznej drogi przez bezpośredni URL.
- Przykładowe wyniki walidacji są oznaczone jako demonstracyjne, bez komunikatu o wykonanym eksporcie lub trwałym podpisie.
- Brak poziomego scrolla całej strony przy 320, 390, 768, 1024, 1366, 1440 i 1920 px. Własny scroll danych dwuwymiarowych jest czytelnie opisany.
- Wszystkie podstawowe przepływy działają klawiaturą, przy zoomie i w obu motywach. Ocena zgodności następuje na wdrożeniu, nie na podstawie makiet.

## Decyzje do potwierdzenia przed implementacją

Rekomendacja: wdrażać powyższy system etapami, zaczynając od wspólnej powłoki i tabel Routing Map. Ciemny motyw pozostaje wariantem początkowym dla obecnych użytkowników, jasny jest równorzędny; preferencja użytkownika ma pierwszeństwo przed systemową. Angielski interfejs pozostaje bez zmian językowych. Nie wprowadzamy nowych struktur DC/VRF/rack ani fałszywego monitoringu. Do przeglądu pozostaje kompozycja i sposób zwijania list podczas edycji; makiety pozwalają ocenić te decyzje przed zmianą działającej aplikacji.
