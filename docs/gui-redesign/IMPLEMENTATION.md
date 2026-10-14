# Wdrożony wariant z nawigacją u góry

Wariant B z TOP-NAVIGATION.md jest wdrożony w warstwie React. Makiety pozostają odniesieniem projektowym, a bieżący kontrakt komponentów i tokenów zapisuje DESIGN.md.

## Zmiany

- Górny pasek: grupy Infrastructure, Diagnostics i Utilities, Workspace, administracja według uprawnień, tenant, konto i przełącznik motywu. Poniżej 1280 px moduły są w menu Modules; ekran telefonu zachowuje tenant i konto. Menu jest renderowane przez portal i obsługuje Escape oraz focus.
- Pełna szerokość treści, wspólny rytm odstępów, przyciski, pola, statusy i lokalne przełączniki widoków. Motywy jasny i ciemny zapisują tylko preferencję wyglądu. Usunięto obowiązkowy import fontów z Google; nazwy fontów mają lokalne/systemowe fallbacki.
- Moduły mają adresy hash, działające odświeżanie oraz Back/Forward. Po zmianie modułu fokus przechodzi do treści. Adresy nie kodują jeszcze selekcji wszystkich obiektów i filtrów.
- IPAM: domyślna lista podsieci z filtrowaniem, osobne widoki modułu i sekcje podsieci, heatmapa jako widok początkowy, z kafelkami 24 × 24 px i odstępem 3 px, kolumnami na całą dostępną szerokość i maksymalnie 20 wierszami na stronę i pobieraniem całego widocznego zakresu partiami do 500 rekordów; tabela pozostaje alternatywą. Tabela i mapa otwierają wspólny inspektor, bez przeskakiwania z tabeli do mapy. Rzadkie akcje podsieci są w More. Zachowano paginację, wersjonowanie, uprawnienia i operacje zbiorcze. Odświeżenie rekordu jest przypisane do generacji wyboru, więc spóźniona odpowiedź nie zastępuje innego wybranego adresu.
- Device Visualization: Fit mierzony z geometrii urządzenia i dostępnej przestrzeni, zoom, fullscreen, tabela portów z wyszukiwaniem, inspektor obok oraz zwijana lista urządzeń. Na telefonie początkowo tabela. Fizyczna kolejność portów pozostaje bez zmian. Zapis edytora nadal jest dokumentacją, nie konfiguracją sprzętu. Przy zbyt małych celach w Fit wybór wymaga zoomu lub tabeli.
- Routing Map: identyczny colgroup dla Interfaces i Routes, stabilne szerokości podczas edycji, mobilny widok label/value. Import jest rozwijanym procesem zamiast stale otwartym formularzem.
- Pozostałe moduły korzystają ze wspólnego wyglądu i nawigacji lokalnej. Ekran startowy jest obsługiwany klawiaturą i opisuje rzeczywistą architekturę self-hosted. Demonstracyjne etapy walidacji są jawnie oznaczone; GUI nie deklaruje eksportu lub trwałego podpisu, których nie wykonało.

## Weryfikacja

- `npm run build`: build produkcyjny przechodzi.
- `npm test`: 24 pliki, 84 testy przechodzą; obejmują uprawnienia grup nawigacji i obliczenia Fit.
- Chromium z izolowanymi przykładowymi odpowiedziami API: 63 kombinacje (Workspace i osiem modułów × 320/390/768/1024/1366/1440/1920 px), bez poziomego overflow całej strony.
- Przepływy przeglądarkowe: inspektor IPAM bez zmiany Table, ochrona niezapisanego draftu, zapis adresu i opóźniona odpowiedź przy zmianie wyboru; Fit całego urządzenia oraz zapis portu; wspólne granice tabel routingu; oba motywy; widoczność menu dla czytelnika IPAM; focus po Escape, wyborze modułu oraz Back/Forward.
- Niezależny przegląd sześciu zrzutów desktop/mobile i źródeł: disposition ship po korekcie fokusu. Jasny motyw sprawdzono po zakończeniu przejść kolorów.
- `graphify update .`: graf kodu odświeżony przez ekstrakcję AST.

Zrzuty rzeczywistej aplikacji z danymi testowymi są w `.impeccable/review/`. Testy przeglądarkowe sprawdzają frontend na fixtures, nie połączenia do rzeczywistych urządzeń ani walidację istniejących roboczych zmian backendu. Nie wykonano pełnego audytu zgodności WCAG. Loader i detektor Impeccable są niedostępne bez zainstalowanego silnika; źródła i niezależny przegląd wykorzystano bezpośrednio.

## Granice obecnego wdrożenia

Lista podsieci jest płaska; zaplanowane pełne drzewo i adresy URL pojedynczych obiektów pozostają dalszym rozszerzeniem. Fit służy do orientacji — nazwy i formularze pozostają czytelne w tabeli i inspektorze. Ochrona niezapisanych zmian obejmuje edytor urządzenia/portu, adresu i nagłówka podsieci; nie jest jeszcze wspólnym systemem Save/Discard/Stay dla wszystkich formularzy projektu. Połączenia, runy walidacji i trwały sign-off nie zostały dodane jako nowe funkcje backendowe. Wdrożenie nie przenosi ani nie zmienia danych tenantów.
