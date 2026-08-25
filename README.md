# autofag

Overvåker emner på UiO Studentweb og melder deg på når en plass blir ledig.

## Kom i gang

Du trenger ingenting installert fra før. `uv` henter både Python og nettleseren.

1. Installer `uv`: `brew install uv`, `winget install astral-sh.uv`, eller
   se https://docs.astral.sh/uv/getting-started/installation/
2. `uv tool install git+https://github.com/vuhnger/autofag`
3. Blir ikke `autofag` funnet: kjør `uv tool update-shell` og åpne en ny terminal
4. `autofag init`
5. Logg inn i vinduet som åpnes
6. Søk opp emnene du vil ha, og velg dem
7. Velg hvordan du vil varsles
8. La den stå og gå

Første kjøring laster ned nettleseren autofag bruker, rundt 150 MB. Det skjer bare én
gang.

Oppdater med `uv tool install --force git+https://github.com/vuhnger/autofag`.
`uv tool uninstall autofag` fjerner verktøyet, men lar emnelista og browserprofilen i
`~/.local/share/autofag` ligge; `autofag logout` sletter profilen.

autofag ser aldri passordet, fødselsnummeret eller PIN-koden din. Innloggingen skjer i
browservinduet, og økten ligger i din egen lokale browserprofil.

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
