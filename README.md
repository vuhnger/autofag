# autofag

Overvåker emner på UiO Studentweb og melder deg på når en plass blir ledig.

## Kom i gang

1. `uv tool install git+https://github.com/vuhnger/autofag`
2. `autofag init`
3. Logg inn i vinduet som åpnes.
4. Søk opp emnene du vil ha, og velg dem.
5. Velg hvordan du vil varsles.
6. La den stå og gå.

Første gang laster autofag ned nettleseren den bruker, og det tar et par minutter.

autofag ser aldri passordet, fødselsnummeret eller PIN-koden din. Innloggingen skjer i
browservinduet, og økten ligger i din egen lokale browserprofil. `autofag logout`
sletter den.

## Nyttige kommandoer

```
autofag init                  sett opp emner og varsling, og start overvåkingen
autofag watch                 gjenoppta en watchlist du alt har satt opp
autofag watch -d              kjør i bakgrunnen og gi terminalen tilbake
autofag stop                  stopp overvåkingen som kjører i bakgrunnen
autofag watch --dry-run       kjør hele løkka, men bekreft aldri en påmelding
autofag status                se hva som overvåkes og hva sist status var
autofag preview IN5170        gå gjennom påmeldingsdialogen uten å bekrefte noe
autofag choose IN5170 "tid og form" "Høst 2026 - Avsluttende skriftlig eksamen"
autofag doctor                sjekk at innlogging, søk og varsling virker
autofag logout                slett den lokale browserprofilen
```

Autofag velger første ledige alternativ i hver nedtrekksliste under påmelding og
forteller deg hva den valgte. Er ingen av alternativene ledige, er emnet fullt selv om
lista sa noe annet, og du får ikke varsel. `autofag choose` overstyrer det per emne.

## Varsling

Du får ett varsel per emne per kjøring, ikke ett per sjekk. Utfallet av en påmelding,
tapt innlogging og oppbrukt timesbudsjett kommer alltid gjennom, uansett tak.

```yaml
notify:
  max_per_course_per_run: 1   # 0 slår av taket
  use_emoji: true             # emojien står i tittelen, så alle kanaler viser den
```
