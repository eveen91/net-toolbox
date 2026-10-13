# Alternatywa B — nawigacja górna

Status: propozycja obok wariantu A z panelem bocznym. Makiety są statyczne, zawierają przykładowe dane i nie zmieniają działającego GUI. Zachowują ten sam system wizualny oraz reguły akcji, filtrów, tabel i inspektorów z [głównego projektu](README.md).

## Makiety 1440 × 900

- [IPAM z szerszą tabelą adresów](ipam-topnav.svg).
- [Device Visualization z szerszym panelem urządzenia](devices-topnav.svg).
- [Routing Map ze wspólnymi granicami kolumn](routing-topnav.svg).

## Kompozycja

Jeden pasek aplikacji o wysokości 60 px:

```text
net::toolbox | Workspace | Infrastructure ▾ | Diagnostics ▾ | Utilities ▾ | Administration | Tenant | Account
```

`Infrastructure` zawiera IPAM, Device Visualization i Routing Map. `Diagnostics` zawiera Troubleshoot, Connection Test i Post-Change Validation. `Utilities` zawiera IP Calculator i Subnet Splitter. Administracja jest dostępna według roli; jej podstrony mają własną lokalną nawigację. Pozycja aktywnego modułu pozostaje czytelna w tytule strony, a grupa w pasku ma zaznaczenie.

Menu otwiera kliknięcie, Enter lub Space, nie sam hover. Podaje pełne nazwy modułów i oznacza aktywny. Escape zamyka i przywraca focus; wejście klawiaturą oraz przechodzenie przez linki musi działać bez myszy. Panel menu wychodzi poza pasek przez portal/popover i nie jest przycinany. Linki pozostają prawdziwymi adresami widoków. Nie nakładać ról ARIA menu bez implementacji kompletnego modelu klawiatury; prosty disclosure z listą linków jest wystarczający.

Pod paskiem: tytuł i główna akcja → lokalna nawigacja modułu → narzędzia danych → obiekt oraz inspektor. Filtry, zakładki i operacje nie migrują do globalnego paska. Nie powstają dodatkowe rzędy globalnej nawigacji.

## Ile miejsca odzyskujemy

Przy 1440 px, marginesach 24 px i inspektorze 334 px:

| Region | A: panel boczny | B: pasek górny |
|---|---:|---:|
| Nawigacja zajmująca szerokość | 216 px | 0 px |
| Obszar pracy wewnątrz marginesów | 1176 px | 1392 px |
| Główna powierzchnia przy otwartym inspektorze i odstępie 16 px | 826 px | 1042 px |
| Wysokość górnego paska | 60 px | 60 px |

Zysk wynosi **216 px szerokości**, około **26% dla głównej powierzchni z inspektorem**. Nie powiększamy czcionek ani nie rozciągamy kontrolek: dodatkowa przestrzeń trafia do danych i canvasu. W makietach Routing Map pierwsze dwie kolumny nadal mają 220 i 240 px; rośnie trzecia, a granice pozostają wspólne dla Interfaces i Routes.

Lista podsieci/urządzeń/hostów nie musi zajmować odzyskanego miejsca. Na laptopie pozostaje selektorem otwierającym przegląd obiektów; podczas edycji miejsce otrzymują dane i inspektor. Na szerokim monitorze można pokazać listę obok szczegółów, zachowując rozsądne minimum szerokości danych. Zamknięcie inspektora oddaje jego szerokość tabeli lub panelowi urządzenia.

## Zachowanie przy różnych szerokościach

- **Od 1280 px:** grupy Workspace/Infrastructure/Diagnostics/Utilities, administracja, tenant i konto w jednym rzędzie. Długie nazwy użytkownika/tenanta skracane wizualnie z dostępną pełną wartością; nie rozszerzają nawigacji. Nazwa tenanta w menu potwierdza jego tożsamość przed zmianą.
- **900–1279 px:** logo, selector `Modules` z bieżącym modułem, tenant i konto; pełna lista narzędzi w rozwijanym panelu z grupami. Nie zmniejszamy tekstu, aby wciskać wszystkie przyciski.
- **Poniżej 900 px:** zwarty nagłówek z nawigacją `Modules`, tenantem i kontem; logo może przejść do panelu nawigacji. Wybór obiektu i inspektor jako kolejne ekrany. Zawartość menu ma własny pionowy scroll, bez poziomego scrolla całej aplikacji.
- **1366 × 768:** zachować kompaktowy nagłówek i stały Save w inspektorze. Fit dopasowuje panel urządzenia do obszaru dostępnego także po odjęciu wysokości toolbarów, nie tylko do szerokości.

Breakpointy to punkt wyjścia do weryfikacji rzeczywistych etykiet, fontów i zoomu. Zmiana tenanta, RBAC, ochrona draftu i wersjonowanie zachowują zasady głównego projektu.

## Porównanie decyzji

| Kryterium | A: panel boczny | B: pasek górny |
|---|---|---|
| Duże tabele i panele portów | Mniej szerokości | Więcej szerokości bez zwiększenia paska |
| Odkrywanie modułów | Wszystkie nazwy stale widoczne | Moduły widoczne po otwarciu grupy |
| Zmiana modułu | Jeden klik | Otwarcie grupy i wybór linku |
| Wzrost liczby narzędzi | Wydłuża listę boczną | Wydłuża listy wewnątrz grup |
| Mały laptop | Wymaga zwijania sidebaru | Zostawia szerokość na dane; nawigacja przechodzi do Modules |
| Przewidywalność pracy w module | Wspólna anatomia | Ta sama anatomia, szerszy obszar pracy |

**Rekomendacja dla zgłoszonych problemów:** wariant B jest lepiej dopasowany do szerokich tabel i wizualizacji urządzeń. Grupowanie menu utrzymuje górny pasek w ryzach, a akcje modułu pozostają pod nim. Ceną jest dodatkowy krok przy zmianie narzędzia. Wdrożenie powinno użyć jednej wybranej powłoki; nie trzeba równolegle utrzymywać dwóch pełnych systemów nawigacji.

## Sprawdzenie przed wdrożeniem

Zweryfikować brak overflow dla długiego tenanta i konta, dostępność menu klawiaturą, poprawny focus po zmianie widoku oraz podział miejsca przy otwartym inspektorze. Potwierdzić Fit na 48 Ethernet + uplinki oraz 48 SFP + 8 QSFP. Makiety mają sprawdzoną składnię SVG i geometrię, ale nie stanowią testu działającego interfejsu w przeglądarce.
