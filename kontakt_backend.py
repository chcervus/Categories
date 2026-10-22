import gi
import threading

gi.require_version('EBook', '1.2')
gi.require_version('EDataServer', '1.2')

from gi.repository import EBook, EDataServer, GLib, EBookContacts



def lade_kontakte(adressbuch_uids=None):
    """Lädt Kontakte aus den angegebenen EDS-Adressbüchern parallel."""
    if adressbuch_uids is None:
        adressbuecher = lade_adressbuecher()
        adressbuch_uids = [adressbuch["uid"] for adressbuch in adressbuecher]

    def lade_ein_adressbuch(uid):
        """Verbindet sich mit einer Quelle und bereitet deren Kontakte auf."""
        registry = EDataServer.SourceRegistry.new_sync(None)
        source = registry.ref_source(uid)
        if source is None:
            return []

        try:
            client = EBook.BookClient.connect_sync(source, 1, None)
            success, contacts = client.get_contacts_sync("", None)
            if not success:
                return []
        except Exception:
            return []

        ergebnis_buch = []
        for contact in contacts:
            kontakt = {
                "name": "",
                "email": [],
                "kategorien": [],
                "uid": "",
                "adressbuch_uid": uid,
                "eds_kontakt": contact,
                "book_client": client,
            }

            for attr in contact.get_attributes():
                feld = attr.get_name().upper()
                werte = [wert.str for wert in attr.get_values_decoded()]

                if feld == "FN":
                    kontakt["name"] = werte[0] if werte else ""
                elif feld == "EMAIL":
                    kontakt["email"].extend(werte)
                elif feld == "CATEGORIES":
                    kontakt["kategorien"].extend(werte)
                elif feld == "UID":
                    kontakt["uid"] = werte[0] if werte else ""

            ergebnis_buch.append(kontakt)
        return ergebnis_buch

    # Die Adressbücher werden parallel geladen; executor.map erhält die
    # ursprüngliche Reihenfolge der Adressbuch-UIDs im Gesamtergebnis.
    from concurrent.futures import ThreadPoolExecutor

    if not adressbuch_uids:
        return []

    with ThreadPoolExecutor(max_workers=min(len(adressbuch_uids), 4)) as executor:
        teil_ergebnisse = list(executor.map(lade_ein_adressbuch, adressbuch_uids))

    return [kontakt for teil in teil_ergebnisse for kontakt in teil]

def lade_adressbuecher():
    """Lädt alle in EDS registrierten Adressbücher."""

    registry = EDataServer.SourceRegistry.new_sync(None)

    quellen = registry.list_sources(
        EDataServer.SOURCE_EXTENSION_ADDRESS_BOOK
    )

    adressbuecher = []

    for quelle in quellen:

        adressbuch = {
            "uid": quelle.get_uid(),
            "name": quelle.get_display_name()
        }

        adressbuecher.append(adressbuch)

    return adressbuecher

# Filter nur einmal kompilieren, Kategorien in Anfuehrungszeichen
# erlauben (auch AND/OR/NOT, Klammern und "Ohne Kategorie").
# Begrenzungen vermeiden rekursionsbedingte Programmabstuerze.
MAX_FILTER_ZEICHEN = 4096
MAX_FILTER_TOKENS = 512
MAX_FILTER_TIEFE = 48


def filter_kategorie_zitieren(name):
    """Sichere Darstellung eines Kategorienamens im Filterausdruck."""
    if name == "__OHNE_KATEGORIE__":
        return "@OHNE_KATEGORIE"
    return '"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"'


def filter_kompilieren(ausdruck, alle_kategorien):
    """Uebersetzt einen Filter in einen wiederverwendbaren Ausdrucksbaum."""
    if len(ausdruck) > MAX_FILTER_ZEICHEN:
        raise ValueError("Filter ist zu lang (maximal 4096 Zeichen).")
    namen = sorted(set(alle_kategorien), key=len, reverse=True)
    tokens = []
    i = 0
    while i < len(ausdruck):
        if ausdruck[i].isspace():
            i += 1
            continue
        if ausdruck[i] in '()':
            tokens.append((ausdruck[i], None)); i += 1
        elif ausdruck[i] == '"':
            i += 1
            chars = []
            while i < len(ausdruck) and ausdruck[i] != '"':
                if ausdruck[i] == "\\":
                    i += 1
                    if i >= len(ausdruck) or ausdruck[i] not in ('"', "\\"):
                        raise ValueError("Ungueltige Escape-Sequenz in Kategorie.")
                chars.append(ausdruck[i]); i += 1
            if i == len(ausdruck):
                raise ValueError("Nicht geschlossenes Anfuehrungszeichen.")
            name = ''.join(chars); i += 1
            if name.casefold() not in {n.casefold() for n in namen}:
                raise ValueError("Unbekannte Kategorie: " + name)
            tokens.append(('CATEGORY', name))
        else:
            rest = ausdruck[i:]
            matched = False
            for op in ('AND', 'OR', 'NOT', '@OHNE_KATEGORIE'):
                if rest.upper().startswith(op) and (len(rest) == len(op) or rest[len(op)].isspace() or rest[len(op)] in '()'):
                    tokens.append((op, None)); i += len(op); matched = True; break
            if not matched:
                # Kompatibilitaet mit frueheren unzitierten Kategorienamen.
                for name in namen + ['Ohne Kategorie']:
                    if rest.casefold().startswith(name.casefold()) and (len(rest) == len(name) or rest[len(name)].isspace() or rest[len(name)] in '()'):
                        tokens.append(('EMPTY', None) if name == 'Ohne Kategorie' else ('CATEGORY', name))
                        i += len(name); matched = True; break
            if not matched:
                raise ValueError("Unbekannter Ausdruck nahe: " + rest[:50])
        if len(tokens) > MAX_FILTER_TOKENS:
            raise ValueError("Zu viele Filterelemente.")
    if not tokens:
        raise ValueError("Leerer Filterausdruck.")
    pos = 0
    def parse_or(depth):
        nonlocal pos
        node = parse_and(depth)
        while pos < len(tokens) and tokens[pos][0] == 'OR':
            pos += 1
            node = ('OR', node, parse_and(depth))
        return node
    def parse_and(depth):
        nonlocal pos
        node = parse_not(depth)
        while pos < len(tokens) and tokens[pos][0] == 'AND':
            pos += 1
            node = ('AND', node, parse_not(depth))
        return node
    def parse_not(depth):
        nonlocal pos
        if depth > MAX_FILTER_TIEFE:
            raise ValueError("Filter ist zu tief verschachtelt.")
        if pos >= len(tokens):
            raise ValueError("Unerwartetes Ende des Filters.")
        kind, value = tokens[pos]
        if kind == 'NOT':
            pos += 1
            return ('NOT', parse_not(depth + 1))
        if kind == '(':
            pos += 1
            node = parse_or(depth + 1)
            if pos >= len(tokens) or tokens[pos][0] != ')':
                raise ValueError("Fehlende schliessende Klammer.")
            pos += 1
            return node
        if kind in ('CATEGORY', 'EMPTY', '@OHNE_KATEGORIE'):
            pos += 1
            return ('EMPTY',) if kind != 'CATEGORY' else ('CATEGORY', value.casefold())
        raise ValueError("Unerwarteter Operator oder Klammer.")
    tree = parse_or(0)
    if pos != len(tokens):
        raise ValueError("Unerwartetes Element am Ende des Filters.")
    return tree


def filter_passt(kategorien, baum):
    """Wertet den kompilierten Filter fuer einen Kontakt aus."""
    normalized = {k.casefold() for k in kategorien}
    def eval_node(node):
        kind = node[0]
        if kind == 'CATEGORY': return node[1] in normalized
        if kind == 'EMPTY': return not normalized
        if kind == 'NOT': return not eval_node(node[1])
        if kind == 'AND': return eval_node(node[1]) and eval_node(node[2])
        return eval_node(node[1]) or eval_node(node[2])
    return eval_node(baum)


def filter_auswerten(kategorien, ausdruck, alle_kategorien):
    """Rueckwaertskompatible Schnittstelle fuer vorhandene Aufrufer."""
    return filter_passt(kategorien, filter_kompilieren(ausdruck, alle_kategorien))


# PHASE 1: Eine frische EDS-Version statt des beim Laden gespeicherten
# EBookContact verändern. Andere Kontaktfelder werden nicht überschrieben.
# Wenn sich Kategorien seit dem Laden geändert haben, nicht blind speichern.
def _kategorien_aus_eds(eds_kontakt):
    kategorien = []
    for attribut in eds_kontakt.get_attributes():
        if attribut.get_name().upper() == "CATEGORIES":
            kategorien.extend(wert.str for wert in attribut.get_values_decoded())
    return kategorien


def _aktuelle_kategorien_speichern(client, kontakt, delta):
    uid = kontakt["uid"]
    if not uid:
        raise ValueError("Kontakt besitzt keine UID und kann nicht gespeichert werden.")

    # EBookClient.get_contact_sync liefert (success, EBookContact).
    erfolg, eds_kontakt = client.get_contact_sync(uid, None)
    if not erfolg or eds_kontakt is None:
        raise RuntimeError("Kontakt konnte vor dem Speichern nicht erneut geladen werden.")

    aktuelle_kategorien = _kategorien_aus_eds(eds_kontakt)
    urspruengliche_kategorien = list(kontakt["kategorien"])
    if sorted(aktuelle_kategorien) != sorted(urspruengliche_kategorien):
        raise RuntimeError(
            "Kategorien wurden zwischenzeitlich extern verändert. "
            "Bitte Kontakte neu laden und Änderungen erneut vornehmen."
        )

    # Nur gewünschte Kategorienänderungen anwenden, übrige
    # vCard-Felder des aktuell geladenen Kontakts unverändert lassen.
    neue_kategorien = list(aktuelle_kategorien)
    for kategorie, vorhanden in delta.items():
        if vorhanden and kategorie not in neue_kategorien:
            neue_kategorien.append(kategorie)
        elif not vorhanden:
            neue_kategorien = [k for k in neue_kategorien if k != kategorie]

    if neue_kategorien != aktuelle_kategorien:
        eds_kontakt.remove_attributes(None, "CATEGORIES")
        for kategorie in neue_kategorien:
            attribut = EBookContacts.VCardAttribute.new(None, "CATEGORIES")
            eds_kontakt.add_attribute_with_value(attribut, kategorie)


        if not client.modify_contact_sync(
            eds_kontakt, EBookContacts.BookOperationFlags.NONE, None
        ):
            raise RuntimeError("EDS hat die Kontaktänderung abgelehnt.")


    return neue_kategorien


def speichere_kategorien(kontakt, neue_kategorien):
    """Kompatible synchrone Schnittstelle; nutzt ebenfalls Versionsprüfung."""
    alte = set(kontakt["kategorien"])
    neue = set(neue_kategorien)
    delta = {k: k in neue for k in alte | neue}
    # PHASE 1: Neuen Client auf aktuellem Thread verbinden.
    registry = EDataServer.SourceRegistry.new_sync(None)
    source = registry.ref_source(kontakt["adressbuch_uid"])
    if source is None:
        raise RuntimeError("Adressbuch ist nicht mehr vorhanden.")
    client = EBook.BookClient.connect_sync(source, 1, None)
    kategorien = _aktuelle_kategorien_speichern(client, kontakt, delta)
    kontakt["kategorien"] = kategorien
    return True


def speichere_kategorien_mehrere_async(kontakte, kontakt_aenderungen, callback):
    """Speichert Änderungen im Worker; Callback im GLib-Hauptthread.

    kontakt_aenderungen: {(adressbuch_uid, kontakt_uid): {kategorie: bool}}
    """
    # PHASE 1: Eingaben kopieren, damit UI-Änderungen laufende Jobs nicht ändern.
    auftraege = []
    for kontakt in kontakte:
        schluessel = (kontakt["adressbuch_uid"], kontakt["uid"])
        if schluessel in kontakt_aenderungen:
            auftraege.append((kontakt, dict(kontakt_aenderungen[schluessel])))


    def fertig_im_hauptthread(erfolge, fehler):
        for kontakt, neue_kategorien in erfolge:
            kontakt["kategorien"] = neue_kategorien
        if fehler:
            callback(RuntimeError(
                f"{len(fehler)} von {len(auftraege)} Kontakten konnten nicht "
                "gespeichert werden. Bereits erfolgreiche Änderungen bleiben bestehen.\n"
                + "\n".join(fehler)
            ))
        else:
            callback(None)
        return GLib.SOURCE_REMOVE

    def arbeiter():
        erfolge, fehler = [], []
        try:
            registry = EDataServer.SourceRegistry.new_sync(None)
            clients = {}
            for kontakt, delta in auftraege:
                try:
                    buch_uid = kontakt["adressbuch_uid"]
                    if buch_uid not in clients:
                        source = registry.ref_source(buch_uid)
                        if source is None:
                            raise RuntimeError("Adressbuch nicht mehr vorhanden.")
                        clients[buch_uid] = EBook.BookClient.connect_sync(
                            source, 1, None
                        )
                    neu = _aktuelle_kategorien_speichern(
                        clients[buch_uid], kontakt, delta
                    )
                    erfolge.append((kontakt, neu))
                except Exception as exc:
                    # Keine Kontaktdaten oder Kategorien in Fehlerlogs ausgeben.
                    fehler.append(f"Kontakt {kontakt.get('uid', '?')}: {exc}")
        except Exception as exc:
            fehler.append(f"Adressbuch-Verbindung fehlgeschlagen: {exc}")
        GLib.idle_add(fertig_im_hauptthread, erfolge, fehler)

    threading.Thread(target=arbeiter, daemon=True).start()
