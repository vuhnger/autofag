from __future__ import annotations

LOGIN_INSTRUCTIONS = (
    "Et nettleservindu åpner seg nå.\n"
    "Logg inn på Studentweb slik du pleier, med ID-porten eller Feide.\n"
    "autofag ser aldri passordet, fødselsnummeret eller PIN-koden din.\n"
    "Når du er inne, tar autofag over av seg selv."
)
LOGIN_DONE = "Innlogget. Økten ligger i din egen lokale nettleserprofil."
LOGIN_FAILED = "Fikk ikke logget inn: {reason}"

SEARCH_PROMPT = "Søk etter emne (emnekode eller navn). Tom linje = ferdig"
SEARCH_FILTER_SUBJECT = "Begrens til fag (valgfritt)"
SEARCH_FILTER_FACULTY = "Begrens til fakultet (valgfritt)"
SEARCH_NO_HITS = "Ingen treff. Prøv et annet søk."
SEARCH_HITS = "{shown} av {total} treff"
SEARCH_MORE_PAGES = "Det finnes flere sider med treff. Snevre inn søket for å se resten."

SELECT_COURSES = "Velg emner: mellomrom merker av, enter bekrefter"
SELECT_SINGLE = "Legg {code} {name} til i watchlisten?"
SELECT_NOTHING_PICKED = "Du merket ikke av noe. Bruk mellomrom for å merke av."
SELECT_SO_FAR = "Valgt så langt: {codes}. Søk videre, eller trykk enter på tomt søk."
SELECT_NONE_YET = "Du har ikke valgt noen emner ennå."
SELECT_ADDED = "Lagt til: {codes}"

WATCH_OPENS_AT = "Vet du når påmeldingen åpner for {code}? (ÅÅÅÅ-MM-DD TT:MM, tom for nei)"
WATCH_BAD_TIMESTAMP = "Forsto ikke tidspunktet. Hopper over det."

CHANNELS_SELECT = "Hvordan vil du varsles? Mellomrom merker av, enter bekrefter"
CHANNELS_NEED_ONE = (
    "Du må velge minst én kanal. Uten varsling får du aldri vite at en plass ble ledig.\n"
    "Bruk mellomrom for å merke av. macOS-varsel krever ingen oppsett."
)
CHANNEL_LABELS = {
    "ntfy": "ntfy.sh, push til mobil (krever et topic)",
    "email": "E-post (krever SMTP-vert og passord)",
    "sms": "SMS via Twilio (krever konto og nøkler)",
    "macos": "macOS-varsel (ingen oppsett)",
}
CHANNEL_NTFY_TOPIC = "ntfy-topic (hold den hemmelig, den er nøkkelen til varslene dine)"
CHANNEL_NTFY_SERVER = "ntfy-server"
CHANNEL_EMAIL_HOST = "SMTP-vert"
CHANNEL_EMAIL_PORT = "SMTP-port"
CHANNEL_EMAIL_USERNAME = "SMTP-brukernavn"
CHANNEL_EMAIL_PASSWORD = "SMTP-passord"
CHANNEL_EMAIL_RECIPIENT = "Send e-post til"
CHANNEL_SMS_SID = "Twilio account SID"
CHANNEL_SMS_TOKEN = "Twilio auth token"
CHANNEL_SMS_FROM = "Twilio-nummer du sender fra"
CHANNEL_SMS_TO = "Telefonnummer som skal varsles"

CHANNEL_TEST_SENDING = "Sender en testvarsling på {channel} ..."
CHANNEL_TEST_CONFIRM = "Kom testvarslingen fram på {channel}?"
CHANNEL_TEST_FAILED = "{channel} svarte: {detail}"
CHANNEL_TEST_RETRY = "Vil du prøve å sette opp {channel} på nytt?"
CHANNEL_DELIVERED_BUT_UNSEEN = (
    "{channel} rapporterte at varselet ble sendt, så oppsettet er riktig.\n"
    "Ser du det ikke, er det som regel varslingstillatelser: "
    "Systeminnstillinger, Varsler, og finn terminalen du kjører autofag fra."
)
CHANNEL_USE_ANYWAY = "Vil du bruke {channel} likevel?"
CHANNEL_NONE_WORKING_RETRY = (
    "Ingen av kanalene virket. Vi tar det på nytt, så du ikke ender opp uten varsling."
)

TEST_NOTIFICATION_TITLE = "autofag virker"
TEST_NOTIFICATION_BODY = "Dette er en testvarsling fra autofag. Du trenger ikke gjøre noe."

REVIEW_HEADER = "Klar til å starte"
REVIEW_COURSES = "Emner"
REVIEW_CHANNELS = "Varsling"
REVIEW_AUTO_ENROLL = "Auto-påmelding"
REVIEW_AUTO_ENROLL_ON = "på for alle emnene i lista"
REVIEW_AUTO_ENROLL_DRY = "av (tørrkjøring, stopper før bekreftelsen)"
REVIEW_CONFIRM = "Starter overvåkingen?"
REVIEW_ABORTED = "Avbrutt. Ingenting er lagret."

WATCH_STARTED = "Overvåker {count} emne(r). La vinduet stå åpent, eller kjør autofag watch senere."
WATCH_NOTHING_TO_DO = "Ingen aktive emner å overvåke. Kjør autofag init først."

DOCTOR_OK = "Alt ser riktig ut. Studentweb-release {release}, {rows} rad(er) parset."
DOCTOR_NO_ROWS = "Fant ingen rader med gjenkjent status. Studentweb har trolig endret seg."
DOCTOR_CHANNELS = "Kanaler: {channels}"

LOGOUT_DONE = "Nettleserprofilen er slettet. Kjør autofag init for å logge inn igjen."
STATUS_EMPTY = "Watchlisten er tom."

NOTIFY_AVAILABLE_TITLE = "Ledig plass: {code}"
NOTIFY_AVAILABLE_BODY = "{code} {name} har ledig plass på undervisningen nå."
NOTIFY_SESSION_EXPIRED_TITLE = "autofag mistet innloggingen"
NOTIFY_SESSION_EXPIRED_BODY = (
    "Kjør `autofag init` for å logge inn igjen. Overvåkingen står stille inntil da."
)
NOTIFY_BUDGET_TITLE = "autofag har brukt opp timesbudsjettet"
NOTIFY_BUDGET_BODY = "{detail}. Overvåkingen er satt på pause."
NOTIFY_UNKNOWN_STATUS_TITLE = "Ukjent status for {code}"
NOTIFY_UNKNOWN_STATUS_BODY = (
    "Studentweb svarte med tekst autofag ikke kjenner igjen:\n{text}\n"
    "Legg frasen inn i status_vocabulary i config."
)

ENROLL_CONFIRMED = "Påmeldt {code}"
ENROLL_WAITLISTED = "Venteliste på {code}"
ENROLL_FULL = "{code} ble fullt før vi rakk det"
ENROLL_REJECTED = "{code} avviste påmeldingen"
ENROLL_UNVERIFIED = "{code}: bekreft manuelt"
ENROLL_ABORTED = "{code}: påmelding avbrutt"
ENROLL_DISABLED = "auto-påmelding er slått av"
ENROLL_ALREADY_DONE = "allerede meldt på i denne kjøringen"
ENROLL_TOO_MANY_UNVERIFIED = "for mange ubekreftede forsøk"
ENROLL_NO_ATTEMPT = "ingen forsøk ble gjort"
ENROLL_VERIFIED_AFTER_DROP = "verifisert etter avbrutt forsøk"
ENROLL_COULD_NOT_VERIFY = "{detail}; kunne ikke verifisere: {error}"
ENROLL_COURSE_MISSING = "{detail}; emnet ble ikke funnet"

BROWSER_PROFILE_IN_USE = (
    "Nettleserprofilen er i bruk av en annen autofag-prosess (pid {pid}).\n"
    "Lukk det vinduet, eller avslutt prosessen, og prøv igjen."
)
BROWSER_PROFILE_IN_USE_UNKNOWN = (
    "Nettleserprofilen er allerede i bruk av et annet Chromium-vindu.\n"
    "Lukk vinduet autofag åpnet tidligere, og prøv igjen."
)
BROWSER_FAILED = "Nettleseren startet ikke: {reason}"

ENROLL_NOT_ONE_ROW = "forventet nøyaktig én rad, fikk {count}"
ENROLL_WRONG_ROW = "raden var {found}, forventet {wanted}"
ENROLL_NOT_TAKEABLE = "raden er ikke ledig: {status}"
ENROLL_DIALOG_MISMATCH = "bekreftelsesdialogen nevnte ikke {code}. Dialogen sa: {excerpt}"
ENROLL_DRY_RUN = "tørrkjøring stoppet før bekreftelse via {control}"
ENROLL_UNRECOGNISED_RESPONSE = "svaret etter bekreftelse ble ikke gjenkjent"

UNEXPECTED_ERROR = (
    "Noe uventet skjedde: {reason}\n"
    "Hele feilen ligger i {log}. autofag har ikke gjort noe halvveis."
)
INTERRUPTED = "Stoppet."
SEARCH_FAILED = "Søket feilet: {reason}. Prøv igjen, eller trykk Ctrl+C for å avslutte."
WATCH_CRASHED = "Overvåkingen stoppet: {reason}"

ENROLL_NEEDS_A_CHOICE = (
    "dialogen krever et valg autofag ikke tar for deg ({fields}). Fullfør påmeldingen manuelt."
)
ENROLL_NO_WAY_FORWARD = "fant ingen trygg knapp å gå videre med. Kontroller i dialogen: {labels}"
ENROLL_TOO_MANY_STEPS = "dialogen tok mer enn {steps} steg, stoppet for sikkerhets skyld"

CHANNEL_PORT_NOT_A_NUMBER = "{answer} er ikke et portnummer. Skriv bare tallet, for eksempel 587."
ENROLL_STILL_UNVERIFIED = "{detail}; emnet står som {status}, så plassen er ikke bekreftet"


PREVIEW_NOT_TAKEABLE = "{code} har ingen ledig plass akkurat nå, så dialogen kan ikke åpnes."
PREVIEW_HEADER = "Påmeldingsdialogen for {code}"
PREVIEW_STEP = "Steg {step}"
PREVIEW_CONTROLS = "Knapper"
PREVIEW_CHOICES = "Valg"
PREVIEW_HOWTO = (
    'Ingenting ble bekreftet. Sett et valg med:\n  autofag choose {code} "<felt>" "<verdi>"'
)
CHOICE_SAVED = "Lagret: {code} velger {value} for {field}."
CHOICE_UNKNOWN_COURSE = "{code} står ikke i watchlisten."

ENROLL_CHOICE_MADE = "Valgte {value} for {field}."
ENROLL_NO_OPTIONS = "{field} hadde ingen alternativer å velge mellom."

DETACHED_STARTED = (
    "Overvåkingen kjører i bakgrunnen (pid {pid}).\nLogg: {log}\nStopp med: autofag stop"
)
DETACHED_ALREADY_RUNNING = "Overvåkingen kjører allerede (pid {pid} på {host})."
STOP_NOT_RUNNING = "Ingen overvåking kjører."
STOP_OTHER_HOST = "Overvåkingen kjører på {host}, ikke her. Stopp den der."
STOP_SENT = "Ba pid {pid} om å stoppe."
STOP_STOPPED = "Overvåkingen er stoppet."
STOP_STILL_RUNNING = "Pid {pid} svarte ikke innen {seconds} sekunder. Stopp den manuelt."

INIT_EXISTING_WATCHLIST = "Du overvåker allerede: {codes}"
INIT_KEEP_EXISTING = "Vil du beholde dem?"
INIT_REMOVED_EXISTING = "Fjernet: {codes}"

ENROLL_NO_FREE_PLACE = "ingen ledig plass i {field}. Studentweb tilbød: {options}"
