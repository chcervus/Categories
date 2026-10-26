import gi
import threading

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gdk, Gio

from kontakt_backend import (
    lade_kontakte,
    lade_adressbuecher,
    filter_auswerten,
    filter_kompilieren, filter_passt, filter_kategorie_zitieren,
    speichere_kategorien_mehrere_async
)


from pathlib import Path

class KontaktfilterWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Categories")
        self.set_default_size(1000, 500)

        self.kontakte = []
        # Generation verhindert, dass veraltete Ladejobs gewinnen.
        self._lade_generation = 0
        self._speichern_aktiv = False
        #  Debounce fuer Texteingaben; Schutz vor Toggle-Rueckkopplung.
        self._filter_timer = None
        self._auswahl_synchronisiert = False
        adressbuecher = lade_adressbuecher()
        self.ausgewaehlte_kontakte = []

        self.ausgewaehlte_kategorien = set()
        self.kategorien_verknuepfung = "OR"

        self.adressbuecher = []
        self.adressbuch_switches = {}
        # Zuordnung ListBoxRow -> Kontakt
        self.zeilen_kontakte = {}
        self.expertenfilter_verwendet = False
        # ---------------------------------------------------------
        # Hauptbereich: vertikales Split-Layout
        # ---------------------------------------------------------

        paned = Gtk.Paned(
            orientation=Gtk.Orientation.HORIZONTAL
        )

        paned.set_position(450)

        # ---------------------------------------------------------
        # LINKE SEITE: Kontakte
        # ---------------------------------------------------------

        linke_seite = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0
        )

        # horizontale Menübox über Kontakteliste links
        kopf_links = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )

        kopf_links.set_margin_top(0)
        kopf_links.set_margin_bottom(12)
        kopf_links.set_margin_start(12)
        kopf_links.set_margin_end(12)


        # Überschrift mit Avatar und Auswahl-Checkbox
        titel_zeile = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8
        )

        self.kontakte_icon = Gtk.Image.new_from_icon_name(
            "avatar-default-symbolic"
        )
        self.kontakte_icon.set_pixel_size(20)
        titel_zeile.append(self.kontakte_icon)

        titel = Gtk.Label(
            label="Kontakte"
        )
        titel.set_xalign(0)
        titel.add_css_class("title-3")

        titel_zeile.append(titel)

        self.auswahl_button = Gtk.CheckButton()
        self.auswahl_button.connect(
            "toggled",
            self.auswahl_button_geaendert
        )
        self.auswahl_button.set_tooltip_text("Alle auswählen")
        self.auswahl_button.set_valign(Gtk.Align.CENTER)

        titel_zeile.append(self.auswahl_button)

        # Überschrift und Status untereinander
        kopf_inhalt = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=15
        )

        kopf_inhalt.append(titel_zeile)

        self.status_label = Gtk.Label(
            label="Kontakte werden geladen …"
        )
        self.status_label.set_xalign(0)
        self.status_label.set_wrap(True)
        self.status_label.add_css_class("dim-label")

        kopf_inhalt.append(self.status_label)

        kopf_links.append(kopf_inhalt)



        abstand = Gtk.Box()
        abstand.set_hexpand(True)
        kopf_links.append(abstand)

        # bearbeiten_button
        self.bearbeiten_button = Gtk.Button()
        self.bearbeiten_button.set_icon_name(
            "document-edit-symbolic"
        )
        self.bearbeiten_button.set_valign(Gtk.Align.START)
        self.bearbeiten_button.set_tooltip_text(
            "Kategorien bearbeiten"
        )
        self.bearbeiten_button.set_sensitive(False)
        self.bearbeiten_button.connect(
            "clicked",
            self.kategorien_bearbeiten
        )

        # E-Mail-Menü
        self.email_button = Gtk.MenuButton()
        self.email_button.set_icon_name("mail-message-new-symbolic")
        self.email_button.set_valign(Gtk.Align.START)
        self.email_button.set_always_show_arrow(True)
        self.email_button.add_css_class("suggested-action")
        self.email_button.set_tooltip_text(
            "E-Mail an ausgewählte Kontakte"
        )

        email_menue = Gio.Menu()
        email_menue.append("An (To)", "win.email-to")
        email_menue.append("CC", "win.email-cc")
        email_menue.append("BCC", "win.email-bcc")

        # Aktionen für die Menüeinträge
        for feld in ("to", "cc", "bcc"):
            aktion = Gio.SimpleAction.new(
                f"email-{feld}",
                None
            )
            aktion.connect(
                "activate",
                self.email_aktion_ausfuehren,
                feld
            )
            self.add_action(aktion)

        self.email_button.set_menu_model(email_menue)
        self.email_button_aktualisieren()
        kopf_links.append(self.bearbeiten_button)
        kopf_links.append(self.email_button)
        linke_seite.append(kopf_links)

        # Kontaktliste

        self.liste = Gtk.ListBox()
        # Stil wie die Navigationssidebar
        self.liste.add_css_class("navigation-sidebar")

        css_datei = Path(__file__).resolve().parent / "style.css"

        css = Gtk.CssProvider()
        css.load_from_path(str(css_datei))

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


        self._kontaktlisten_css = css

        self.liste.set_selection_mode(
            Gtk.SelectionMode.MULTIPLE
        )

        klick_geste = Gtk.GestureClick()

        klick_geste.set_propagation_phase(
            Gtk.PropagationPhase.CAPTURE
        )

        klick_geste.connect(
            "pressed",
            self.kontakt_geklickt
        )

        self.liste.add_controller(
            klick_geste
        )

        key_controller = Gtk.EventControllerKey()

        key_controller.connect(
            "key-pressed",
            self.liste_tastatur
        )

        self.add_controller(
            key_controller
        )

        self.liste.connect(
            "row-selected",
            self.kontakt_ausgewaehlt
        )

        # ScrolledWindow
        scroll = Gtk.ScrolledWindow()

        scroll.set_vexpand(True)
        scroll.set_hexpand(True)

        scroll.set_child(self.liste)

        linke_seite.append(scroll)

        # ---------------------------------------------------------
        # RECHTE SEITE
        # ---------------------------------------------------------

        rechte_seite = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )

        rechte_seite.set_margin_top(0)
        rechte_seite.set_margin_bottom(12)
        rechte_seite.set_margin_start(12)
        rechte_seite.set_margin_end(12)

        # Adressbücher
        adressbuch_titel_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8
        )

        adressbuch_icon = Gtk.Image.new_from_icon_name(
            "x-office-address-book-symbolic"
        )
        adressbuch_icon.set_pixel_size(20)
        adressbuch_titel_box.append(adressbuch_icon)

        adressbuch_titel = Gtk.Label(
            label="Adressbücher"
        )
        adressbuch_titel.set_xalign(0)
        adressbuch_titel.add_css_class("title-3")

        adressbuch_titel_box.append(adressbuch_titel)
        rechte_seite.append(adressbuch_titel_box)

        self.adressbuch_bereich = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0
        )
        self.adressbuch_bereich.add_css_class("separated")
        # Alle Adressbücher als gemeinsamer, weiß hinterlegter Bereich.
        self.adressbuch_bereich.add_css_class("card")
        self.adressbuch_bereich.set_margin_top(4)
        self.adressbuch_bereich.set_margin_bottom(4)
        self.adressbuch_bereich.set_margin_start(4)
        self.adressbuch_bereich.set_margin_end(4)

        rechte_seite.append(self.adressbuch_bereich)
        self.adressbuecher_anzeigen()

        # Trennlinie
        trennlinie = Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL
        )

        rechte_seite.append(trennlinie)


         # Filter
        filter_titel_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8
        )

        filter_icon = Gtk.Image.new_from_icon_name(
            "go-down-symbolic"
        )
        filter_icon.set_pixel_size(20)
        filter_titel_box.append(filter_icon)

        heading_label = Gtk.Label(label="Filter")
        heading_label.set_xalign(0)
        heading_label.add_css_class("title-3")

        filter_titel_box.append(heading_label)
        rechte_seite.append(filter_titel_box)





        # Kategorien
        kategorien_titel_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8
        )
        kategorien_titel_box.set_margin_top(12)
        kategorien_titel_box.set_margin_start(12)
        kategorien_icon = Gtk.Image.new_from_icon_name(
            "preferences-color-symbolic"
                )
        kategorien_icon.set_pixel_size(20)
        kategorien_titel_box.append(kategorien_icon)

        kategorien_titel = Gtk.Label(
            label="Kategorien"
        )
        kategorien_titel.set_xalign(0)
        kategorien_titel.add_css_class("heading")

        kategorien_titel_box.append(kategorien_titel)


        # Gemeinsame Karte für Kategorien und Verknüpfung
        kategorien_karte = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0
        )
        kategorien_karte.add_css_class("card")
        kategorien_karte.set_margin_top(4)
        kategorien_karte.set_margin_bottom(4)
        kategorien_karte.set_margin_start(4)
        kategorien_karte.set_margin_end(4)
        #Überschrift innerhalb der Karte
        kategorien_karte.append(kategorien_titel_box)





        self.kategorien_bereich = Gtk.FlowBox()
        self.kategorien_bereich.set_margin_start(12)
        self.kategorien_bereich.set_margin_end(12)
        self.kategorien_bereich.set_margin_top(12)
        self.kategorien_bereich.set_margin_bottom(12)
        self.kategorien_bereich.set_selection_mode(
            Gtk.SelectionMode.NONE
        )

        self.kategorien_bereich.set_row_spacing(6)
        self.kategorien_bereich.set_column_spacing(6)

        kategorien_karte.append(
            self.kategorien_bereich
        )


        # Trennlinie zwischen Kategorien und Verknüpfung
        kategorien_trennlinie = Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL
        )
        kategorien_karte.append(kategorien_trennlinie)



        # Innenabstand durch einen umgebenden Container
        verknuepfung_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )
        verknuepfung_box.set_margin_top(12)
        verknuepfung_box.set_margin_bottom(12)
        verknuepfung_box.set_margin_start(12)
        verknuepfung_box.set_margin_end(12)
        verknuepfung_box.set_hexpand(True)

        verknuepfung_titel = Gtk.Label(
            label="Kategorien verknüpfen"
        )
        verknuepfung_titel.set_xalign(0)
        verknuepfung_titel.set_hexpand(True)
        verknuepfung_box.append(verknuepfung_titel)

        self.verknuepfung_gruppe = Adw.ToggleGroup.new()
        self.verknuepfung_gruppe.add_css_class("round")
        self.verknuepfung_gruppe.set_homogeneous(True)

        self.or_toggle = Adw.Toggle.new()
        self.or_toggle.set_name("or")
        self.or_toggle.set_label("Zusammenführen")
        self.verknuepfung_gruppe.add(self.or_toggle)

        self.and_toggle = Adw.Toggle.new()
        self.and_toggle.set_name("and")
        self.and_toggle.set_label("Überlappen")
        self.verknuepfung_gruppe.add(self.and_toggle)

        self.verknuepfung_gruppe.set_active_name("or")
        self.verknuepfung_gruppe.connect(
            "notify::active-name",
            self.verknuepfung_geaendert
        )

        verknuepfung_box.append(
            self.verknuepfung_gruppe
        )

        kategorien_karte.append(verknuepfung_box)
        rechte_seite.append(kategorien_karte)

        # Trennlinie vor dem Expertenmodus
        experten_trennlinie = Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL
        )
        rechte_seite.append(experten_trennlinie)



    # Expertenmodus

            # Expertenmodus-Karte
        experten_karte = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0
        )
        experten_karte.add_css_class("card")
        experten_karte.set_margin_top(4)
        experten_karte.set_margin_bottom(4)
        experten_karte.set_margin_start(4)
        experten_karte.set_margin_end(4)

        # Innenabstand innerhalb der Karte
        experten_inhalt = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )
        experten_inhalt.set_margin_top(12)
        experten_inhalt.set_margin_bottom(12)
        experten_inhalt.set_margin_start(12)
        experten_inhalt.set_margin_end(12)

        experten_karte.append(experten_inhalt)

        # Überschrift Expertenmodus
        filter_kopf = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6
        )

        self.experten_button = Gtk.Button.new_from_icon_name(
            "preferences-other-symbolic"
        )
        self.experten_button.set_child(
            Gtk.Image.new_from_icon_name(
                "preferences-other-symbolic"
            )
        )
        self.experten_button.get_child().set_pixel_size(20)
        self.experten_button.set_tooltip_text(
            "Expertenmodus ein- oder ausblenden"
        )
        self.experten_button.connect(
            "clicked",
            self.expertenmodus_umschalten
        )

        filter_kopf.append(self.experten_button)

        filter_titel = Gtk.Label(
            label="Expertenmodus"
        )
        filter_titel.set_xalign(0)
        filter_titel.add_css_class("heading")

        filter_kopf.append(filter_titel)
        experten_inhalt.append(filter_kopf)

        # Filtereingabe
        self.filter_entry = Gtk.Entry()
        self.filter_entry.set_hexpand(True)
        self.filter_entry.set_placeholder_text(
            "Filter, z. B. Freunde AND Verein"
        )
        self.filter_entry.connect(
            "notify::has-focus",
            self.filter_fokus_geaendert
        )
        self.filter_entry.connect(
            "activate",
            self.filter_anwenden
        )
        self.filter_entry.connect(
            "changed",
            self.filter_geaendert
        )

        # Filtereingabe und Lösch-Button
        self.filter_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6
        )
        self.filter_box.set_hexpand(True)

        filter_zeile = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6
        )
        filter_zeile.set_hexpand(True)

        filter_zeile.append(self.filter_entry)

        loeschen_button = Gtk.Button.new_from_icon_name(
            "edit-clear-symbolic"
        )
        loeschen_button.set_tooltip_text(
            "Filterregel löschen"
        )
        loeschen_button.connect(
            "clicked",
            self.expertenregel_loeschen
        )
        filter_zeile.append(loeschen_button)

        self.filter_box.append(filter_zeile)

        # Erklärung unter der Eingabezeile
        experten_hinweis = Gtk.Label(
            label=(
                "Erlaubte Operatoren: AND, OR und NOT. "
                "Klammern ermöglichen verschachtelte Filter."
            )
        )
        experten_hinweis.set_xalign(0)
        experten_hinweis.set_wrap(True)
        experten_hinweis.add_css_class("dim-label")
        experten_hinweis.add_css_class("caption")

        self.filter_box.append(experten_hinweis)

        self.filter_box.set_visible(False)
        experten_inhalt.append(self.filter_box)

        rechte_seite.append(experten_karte)



        # ---------------------------------------------------------
        # Paned zusammensetzen
        # ---------------------------------------------------------


        paned.set_start_child(linke_seite)
        paned.set_end_child(rechte_seite)

        # Hauptbereich mit Titelleiste
        hauptbereich = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0
        )



        # Titelleiste
        kopfzeile = Adw.HeaderBar()
        kopfzeile.add_css_class("flat")
        # Hamburger-Menü
        menue_button = Gtk.MenuButton()
        menue_button.set_icon_name("open-menu-symbolic")
        menue_button.set_tooltip_text("Menü")

        # Menü erstellen
        menue = Gio.Menu()
        menue.append("Info zu Categories", "win.ueber")
        menue_button.set_menu_model(menue)
        kopfzeile.pack_end(menue_button)

        # Menüaktion
        ueber_aktion = Gio.SimpleAction.new("ueber", None)
        ueber_aktion.connect(
            "activate",
            self.ueber_categories_anzeigen
        )
        self.add_action(ueber_aktion)


        # Fenstertitel
        titel_fenster = Gtk.Label(label="")
        titel_fenster.add_css_class("title-2")
        kopfzeile.set_title_widget(titel_fenster)

        hauptbereich.append(kopfzeile)
        hauptbereich.append(paned)

        self.set_content(hauptbereich)



        # ---------------------------------------------------------
        # Kontakte im Hintergrund laden
        # ---------------------------------------------------------
        aktive_uids = self.aktive_adressbuch_uids()

        # PHASE 1: Jede neue Auswahl invalidiert ältere Hintergrundjobs.
        self.kontakte_laden_starten(aktive_uids)
    # =============================================================
    # Menue ueber Kontaktzeile
    # =============================================================
    def auswahl_button_geaendert(self, button):
        # PHASE 3: Programmgesteuerte Updates duerfen kein Toggle ausloesen.
        if self._auswahl_synchronisiert:
            return
        if button.get_active():
            if len(self.ausgewaehlte_kontakte) != len(self.kontakte):
                self.auswahl_alle()
        else:
            if len(self.ausgewaehlte_kontakte) != 0:
                self.auswahl_aufheben()
    # =============================================================
    # Adressbuecher
    # =============================================================
    def adressbuecher_anzeigen(self):

        self.adressbuecher = lade_adressbuecher()

        # Alten Inhalt entfernen
        while child := self.adressbuch_bereich.get_first_child():
            self.adressbuch_bereich.remove(child)

        self.adressbuch_switches = {}

        for adressbuch in self.adressbuecher:

            zeile = Adw.ActionRow()

            zeile.set_title(
                adressbuch["name"]
            )

            switch = Gtk.Switch()

            switch.set_active(True)

            switch.set_valign(
                Gtk.Align.CENTER
            )
            # notify::active sieht den bereits aktualisierten Zustand.
            switch.connect(
                "notify::active",
                self.adressbuch_switch_geaendert,
                adressbuch["uid"]
            )
            zeile.add_suffix(switch)


            self.adressbuch_bereich.append(zeile)

            if adressbuch != self.adressbuecher[-1]:
                separator = Gtk.Separator(
                    orientation=Gtk.Orientation.HORIZONTAL
                )
                self.adressbuch_bereich.append(separator)


            self.adressbuch_switches[
                adressbuch["uid"]
            ] = switch

    def aktive_adressbuch_uids(self):

        aktive_uids = []

        for uid, schalter in self.adressbuch_switches.items():

            if schalter.get_active():
                aktive_uids.append(uid)

        return aktive_uids


    def adressbuch_switch_geaendert(
        self,
        switch,
        param,
        adressbuch_uid
    ):
        # PHASE 1: Aktiven Schalterzustand erst nach dessen Änderung lesen.
        if self._speichern_aktiv:
            return
        # Nur beim Deaktivieren zurücksetzen
        if not switch.get_active():

            # Ausgewählte Kategorien zurücksetzen
            self.ausgewaehlte_kategorien.clear()

            # Grüne Markierungen aller Kategorie-Buttons entfernen
            for button in self.kategorie_buttons.values():
                button.remove_css_class("success")

            # Expertenfilter leeren
            self.filter_entry.set_text("")

            # Expertenmodus verlassen
            self.filter_box.set_visible(False)
            self.expertenfilter_verwendet = False

            # Verknüpfung auf OR zurücksetzen
            self.kategorien_verknuepfung = "OR"
            self.verknuepfung_gruppe.set_active_name("or")

            # Kontaktauswahl zurücksetzen
            self.liste.unselect_all()
            self.ausgewaehlte_kontakte = []

        # Aktive Adressbücher ermitteln
        aktive_uids = self.aktive_adressbuch_uids()

        # PHASE 1: Vorherige Ladejobs dürfen dieses Ergebnis nicht überschreiben.
        self.kontakte_laden_starten(aktive_uids)



    def kontakt_zeile_erstellen(self, kontakt):

        zeile = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )

        zeile.set_margin_top(8)
        zeile.set_margin_bottom(8)
        zeile.set_margin_start(12)
        zeile.set_margin_end(12)

        # ---------------------------------------------------------
        # Avatar
        # ---------------------------------------------------------

        name = kontakt["name"]

        avatar = Adw.Avatar(
            size=48,
            text=name
        )

        zeile.append(avatar)

        # ---------------------------------------------------------
        # Informationen
        # ---------------------------------------------------------

        infos = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3
        )

        infos.set_hexpand(True)

        # Name
        name_label = Gtk.Label(
            label=name
        )

        name_label.set_xalign(0)
        name_label.add_css_class("heading")

        infos.append(name_label)

        # E-Mail
        if kontakt["email"]:

            email = Gtk.Label(
                label=", ".join(kontakt["email"])
            )

            email.set_xalign(0)
            email.set_ellipsize(3)
            email.add_css_class("dim-label")

            infos.append(email)

        # Kategorien
        if kontakt["kategorien"]:

            kategorien = Gtk.Label(
                label=", ".join(kontakt["kategorien"])
            )

            kategorien.set_xalign(0)
            kategorien.set_ellipsize(3)
            kategorien.add_css_class("dim-label")

            infos.append(kategorien)

        zeile.append(infos)

        # ---------------------------------------------------------
        # ListBoxRow
        # ---------------------------------------------------------

        row = Gtk.ListBoxRow()

        row.set_child(zeile)

        self.zeilen_kontakte[row] = kontakt

        return row


    # =============================================================
    # Kontakt ausgewählt
    # =============================================================
    def auswahl_alle(self):

        self.liste.select_all()

        self.ausgewaehlte_kontakte = []

        child = self.liste.get_first_child()

        while child is not None:

            if child.is_selected():

                kontakt = self.zeilen_kontakte.get(child)

                if kontakt is not None:
                    self.ausgewaehlte_kontakte.append(
                        kontakt
                    )

            child = child.get_next_sibling()

        self.auswahl_aktualisieren()

        self.email_button_aktualisieren()
        self.bearbeiten_button.set_sensitive(
            len(self.ausgewaehlte_kontakte) > 0
        )


    def auswahl_aufheben(self):

        self.liste.unselect_all()
        self.ausgewaehlte_kontakte = []
        self.auswahl_aktualisieren()
        self.email_button_aktualisieren()
        self.bearbeiten_button.set_sensitive(False)

    def auswahl_aktualisieren(self):

        anzahl = len(
            self.ausgewaehlte_kontakte
        )

        anzahl_sichtbar = 0

        zeile = self.liste.get_first_child()

        while zeile is not None:

            anzahl_sichtbar += 1
            zeile = zeile.get_next_sibling()


        self._auswahl_synchronisiert = True
        try:
            self.auswahl_button.set_active(
                anzahl == anzahl_sichtbar and anzahl_sichtbar > 0
            )
        finally:
            self._auswahl_synchronisiert = False

        self.status_label.set_text(
            f"{anzahl_sichtbar} gefunden - "
            f"{anzahl} ausgewählt"
        )

    def liste_tastatur(
        self,
        controller,
        keyval,
        keycode,
        state
    ):
        # Strg + A
        if (
            keyval == Gdk.KEY_a
            and state & Gdk.ModifierType.CONTROL_MASK
        ):

            self.auswahl_alle()

            return True

        return False

    def kontakt_ausgewaehlt(self, liste, row):

        self.ausgewaehlte_kontakte = []

        zeile = self.liste.get_first_child()

        while zeile is not None:

            if zeile.is_selected():

                kontakt = self.zeilen_kontakte.get(zeile)

                if kontakt is not None:
                    self.ausgewaehlte_kontakte.append(
                        kontakt
                    )

            zeile = zeile.get_next_sibling()

        self.auswahl_aktualisieren()
        self.email_button_aktualisieren()
        self.bearbeiten_button.set_sensitive(
            len(self.ausgewaehlte_kontakte) > 0
        )
# Wenn man einen ausgewählten Kontakt nochmal anklickt
    def kontakt_geklickt(
        self,
        gesture,
        anzahl_klicks,
        x,
        y
    ):

        zeile = self.liste.get_row_at_y(y)

        if zeile is None:
            return
        # Wir übernehmen diesen Mausklick selbst.
        gesture.set_state(
            Gtk.EventSequenceState.CLAIMED
        )

        if zeile.is_selected():
            self.liste.unselect_row(zeile)
        else:
            self.liste.select_row(zeile)


    # PHASE 2: Grundvalidierung gegen defekte mailto-URIs und Steuerzeichen.
    @staticmethod
    def gueltige_email(adresse):
        if not isinstance(adresse, str) or len(adresse) > 254:
            return False
        if any(ord(zeichen) < 33 or ord(zeichen) == 127 for zeichen in adresse):
            return False
        lokal, sep, domain = adresse.rpartition("@")
        return bool(sep and lokal and domain and "." in domain
                    and not domain.startswith(".") and not domain.endswith("."))

    def email_fehler_anzeigen(self, text):
        dialog = Adw.MessageDialog(
            transient_for=self, modal=True,
            heading="E-Mail konnte nicht vorbereitet werden", body=text
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def email_aktion_ausfuehren(
            self,
            aktion,
            parameter,
            feld
        ):
        # E-Mail-Adressen der ausgewählten Kontakte sammeln
        adressen = []

        for kontakt in self.ausgewaehlte_kontakte:
            for adresse in kontakt.get("email", []):
                adresse = adresse.strip()

                if self.gueltige_email(adresse) and adresse not in adressen:
                    adressen.append(adresse)

        # Prüfen, ob E-Mail-Adressen vorhanden sind
        if not adressen:
            return

        # Empfängerfeld für mailto vorbereiten
        from urllib.parse import urlencode

        empfaenger = ",".join(adressen)
        uri = "mailto:?" + urlencode({feld: empfaenger})
        # PHASE 2: Grenzen der Zielanwendung nicht unkontrolliert ueberschreiten.
        if len(uri) > 1800:
            self.email_fehler_anzeigen(
                "Zu viele Empfaenger fuer einen mailto-Link. "
                "Bitte weniger Kontakte auswaehlen."
            )
            return

        # Standard-E-Mail-Programm öffnen
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error as fehler:
            self.email_fehler_anzeigen(str(fehler))


    def email_button_aktualisieren(self):
        # Prüfen, ob mindestens eine ausgewählte Person
        # eine E-Mail-Adresse besitzt
        email_vorhanden = any(
            self.gueltige_email(adresse.strip())
            for kontakt in self.ausgewaehlte_kontakte
            for adresse in kontakt.get("email", [])
            if isinstance(adresse, str)
        )

        # Button nur aktivieren, wenn eine E-Mail-Adresse vorhanden ist
        self.email_button.set_sensitive(email_vorhanden)

        if email_vorhanden:
            self.email_button.add_css_class("suggested-action")
        else:
            self.email_button.remove_css_class("suggested-action")
    # =============================================================
    # Filter anwenden
    # =============================================================


    # PHASE 3: Texteingabe um 200 ms entprellen, Enter wirkt unmittelbar.
    def filter_geaendert(self, entry):
        if self._filter_timer is not None:
            GLib.source_remove(self._filter_timer)
        self._filter_timer = GLib.timeout_add(200, self._filter_verzoegert)

    def _filter_verzoegert(self):
        self._filter_timer = None
        self.filter_anwenden(self.filter_entry)
        return GLib.SOURCE_REMOVE

    def filter_anwenden(self, entry):
        # PHASE 2/3: Einmal parsen, danach gegen alle Kontakte auswerten.
        if self._filter_timer is not None:
            GLib.source_remove(self._filter_timer)
            self._filter_timer = None
        ausdruck = entry.get_text().strip()
        passende_kontakte = self.kontakte
        if ausdruck:
            alle_kategorien = sorted({
                k for kontakt in self.kontakte for k in kontakt["kategorien"]
            })
            try:
                baum = filter_kompilieren(ausdruck, alle_kategorien)
                passende_kontakte = [
                    k for k in self.kontakte
                    if filter_passt(k["kategorien"], baum)
                ]
            except ValueError as fehler:
                # Eine unvollstaendige Eingabe ist kein leerer Trefferbestand.
                self.status_label.set_text(f"Filterfehler: {fehler}")
                return
        passende_kontakte = sorted(
            passende_kontakte, key=lambda k: k.get("name", "").casefold()
        )
        self.liste.unselect_all()
        self.ausgewaehlte_kontakte = []
        while child := self.liste.get_first_child():
            self.liste.remove(child)
        self.zeilen_kontakte = {}
        for kontakt in passende_kontakte:
            self.liste.append(self.kontakt_zeile_erstellen(kontakt))
        self.auswahl_aktualisieren()
        self.email_button_aktualisieren()
        self.bearbeiten_button.set_sensitive(False)


    # Kategoriebuttons erzeugen immer eindeutig gequotete Werte.
    def kategorienfilter_aktualisieren(self):
        kategorien = [filter_kategorie_zitieren(k)
                      for k in sorted(self.ausgewaehlte_kategorien)]
        self.filter_entry.set_text(
            f" {self.kategorien_verknuepfung} ".join(kategorien)
        )

    def verknuepfung_geaendert(self, gruppe, param):

        if self.filter_box.get_visible():
            return

        auswahl = gruppe.get_active_name()

        if auswahl == "and":
            self.kategorien_verknuepfung = "AND"
        else:
            self.kategorien_verknuepfung = "OR"

        self.kategorienfilter_aktualisieren()

    def expertenregel_loeschen(self, button):

        # Nur die Expertenregel löschen
        self.filter_entry.set_text("")

        # Expertenmodus bleibt aktiv:
        # Kategoriebuttons und Verknüpfung bleiben deaktiviert
        self.filter_fokus_geaendert(None, None)


    def expertenmodus_umschalten(self, button):

        sichtbar = not self.filter_box.get_visible()

        # Filterfeld leeren, bevor der Modus gewechselt wird
        self.filter_entry.set_text("")

        # Modus umschalten
        self.filter_box.set_visible(sichtbar)
        if sichtbar:
            self.experten_button.add_css_class("success")
        else:
            self.experten_button.remove_css_class("success")

        # Zustand zurücksetzen
        self.ausgewaehlte_kategorien.clear()
        self.expertenfilter_verwendet = sichtbar

        # Kategoriebuttons optisch zurücksetzen
        for kategorie, kategorie_button in self.kategorie_buttons.items():
            kategorie_button.remove_css_class("success")

        # Bedienbarkeit an den neuen Modus anpassen
        self.filter_fokus_geaendert(None, None)

        if sichtbar:
            self.filter_entry.grab_focus()



    def filter_fokus_geaendert(self, widget, param):

        expertenmodus = self.filter_box.get_visible()

        # Kategoriebuttons im Expertenmodus deaktivieren
        for kategorie, button in self.kategorie_buttons.items():
            button.set_sensitive(not expertenmodus)

            if expertenmodus or self.expertenfilter_verwendet:
                button.remove_css_class("success")
            elif kategorie in self.ausgewaehlte_kategorien:
                button.add_css_class("success")
            else:
                button.remove_css_class("success")

        # Verknüpfungsauswahl deaktivieren
        self.verknuepfung_gruppe.set_sensitive(
            not expertenmodus
        )

    def kategorien_anzeigen(self):

        # Kategorien leeren
        while child := self.kategorien_bereich.get_first_child():
            self.kategorien_bereich.remove(child)

        kategorien = set()

        for kontakt in self.kontakte:

            for kategorie in kontakt["kategorien"]:

                kategorie = kategorie.strip()

                if kategorie:
                    kategorien.add(kategorie)

        self.kategorie_buttons = {}

        # ---------------------------------------------------------
        # Kategorien
        # ---------------------------------------------------------
        # Ohne Kategorie
        button = Gtk.Button(
            label="Ohne Kategorie"
        )
        self.kategorie_buttons["__OHNE_KATEGORIE__"] = button
        if (
            "__OHNE_KATEGORIE__" in self.ausgewaehlte_kategorien
            and not self.filter_box.get_visible()
            and not self.expertenfilter_verwendet
        ):
            button.add_css_class("success")


        button.add_css_class("pill")

        button.connect(
            "clicked",
            self.kategorie_geklickt,
            "__OHNE_KATEGORIE__"
        )

        self.kategorien_bereich.append(
            button
        )
        for kategorie in sorted(
            kategorien,
            key=str.casefold
        ):

            button = Gtk.Button(
                label=kategorie
            )


            button.add_css_class("pill")

            button.connect(
                "clicked",
                self.kategorie_geklickt,
                kategorie
            )

            self.kategorien_bereich.append(
                button
            )

            self.kategorie_buttons[kategorie] = button

            if (
                kategorie in self.ausgewaehlte_kategorien
                and not self.filter_box.get_visible()
                and not self.expertenfilter_verwendet
            ):
                button.add_css_class("success")

    def kategorie_geklickt(self, button, kategorie):

        # Kategorie auswählen oder abwählen
        if kategorie in self.ausgewaehlte_kategorien:
            self.ausgewaehlte_kategorien.remove(kategorie)
            button.remove_css_class("success")
        else:
            self.ausgewaehlte_kategorien.add(kategorie)
            button.add_css_class("success")


        self.kategorienfilter_aktualisieren()

    def operator_geklickt(
        self,
        button,
        operator
    ):

        ausdruck = self.filter_entry.get_text().strip()

        if not ausdruck:
            return

        if operator == "NOT":

            if ausdruck.upper().endswith(
                ("AND", "OR", "NOT")
            ):
                neuer_ausdruck = (
                    ausdruck
                    + " NOT"
                )
            else:
                neuer_ausdruck = (
                    ausdruck
                    + " AND NOT"
                )

        else:

            if ausdruck.upper().endswith(
                ("AND", "OR", "NOT")
            ):
                return

            neuer_ausdruck = (
                ausdruck
                + " "
                + operator
            )

            self.filter_entry.set_text(
                neuer_ausdruck
            )
    # =============================================================
    # Kontakte laden
    # =============================================================

    # PHASE 1: Ein Hintergrundjob darf GTK-Zustand nicht direkt verändern.
    # Nur die jüngste Generation wird auf dem GTK-Hauptthread übernommen.
    def kontakte_laden_starten(self, adressbuch_uids):
        self._lade_generation += 1
        generation = self._lade_generation
        threading.Thread(
            target=self.kontakte_laden,
            args=(list(adressbuch_uids), generation),
            daemon=True
        ).start()

    def kontakte_laden(self, adressbuch_uids, generation):
        try:
            kontakte = lade_kontakte(adressbuch_uids)
            fehler = None
        except Exception as exc:
            kontakte = None
            fehler = str(exc)
        GLib.idle_add(self.kontakte_laden_fertig, generation, kontakte, fehler)

    def kontakte_laden_fertig(self, generation, kontakte, fehler):
        if generation != self._lade_generation:
            return GLib.SOURCE_REMOVE
        if fehler is not None:
            self.status_label.set_text("Kontakte konnten nicht geladen werden")
            self.ladefehler_anzeigen(fehler)
            return GLib.SOURCE_REMOVE
        self.kontakte = kontakte
        self.kontakte_anzeigen()
        return GLib.SOURCE_REMOVE

    def ladefehler_anzeigen(self, fehler):
        dialog = Adw.MessageDialog(
            transient_for=self, modal=True,
            heading="Laden fehlgeschlagen", body=fehler
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    # =============================================================
    # Kontakte anzeigen
    # =============================================================

    def kontakte_anzeigen(self):

        while child := self.liste.get_first_child():
            self.liste.remove(child)

        self.zeilen_kontakte = {}

        self.status_label.set_text(
            f"{len(self.kontakte)} Kontakte"
        )

        # Alphabetisch nach Vorname, dann Nachname sortieren
        self.kontakte.sort(
            key=lambda kontakt: kontakt.get(
                "name", "").casefold()
        )

        for kontakt in self.kontakte:

            row = self.kontakt_zeile_erstellen(
                kontakt
            )

            self.liste.append(row)

        self.auswahl_aktualisieren()
        self.kategorien_anzeigen()
        # Bestehenden Filter nach dem Neuladen erneut anwenden
        if self.filter_entry.get_text().strip():
            self.filter_anwenden(self.filter_entry)

        return GLib.SOURCE_REMOVE

    def kategorien_bearbeiten(self, button):
        fenster = Adw.Window(
            title="Kategorien bearbeiten",
            transient_for=self,
            modal=True
        )

        fenster.set_default_size(400, 450)
        fenster.set_resizable(True)

        hauptbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )
        aenderungen = {}
        hauptbox.set_margin_top(18)
        hauptbox.set_margin_bottom(18)
        hauptbox.set_margin_start(18)
        hauptbox.set_margin_end(18)
        hauptbox.set_vexpand(True)

        titel = Gtk.Label(
            label=f"{len(self.ausgewaehlte_kontakte)} Kontakte ausgewählt"
        )
        titel.add_css_class("title-3")
        titel.set_halign(Gtk.Align.START)

        hauptbox.append(titel)

        kategorien = sorted({
            kategorie
            for kontakt in self.kontakte
            for kategorie in kontakt["kategorien"]
        })

        kategorien_box = Gtk.Grid()
        kategorien_box.set_column_spacing(24)
        kategorien_box.set_row_spacing(6)

        for index, kategorie in enumerate(kategorien):
            anzahl = sum(
                kategorie in kontakt["kategorien"]
                for kontakt in self.ausgewaehlte_kontakte
            )

            checkbox = Gtk.CheckButton(label=kategorie)

            if anzahl == len(self.ausgewaehlte_kontakte):
                checkbox.set_active(True)
            elif anzahl > 0:
                checkbox.set_inconsistent(True)

            def checkbox_geaendert(checkbutton, name=kategorie):
                # Der Zwischenzustand endet mit dem ersten Klick.
                checkbutton.set_inconsistent(False)

                # Gewünschten Zustand für alle Kontakte merken.
                aenderungen[name] = checkbutton.get_active()

            checkbox.connect("toggled", checkbox_geaendert)
            zeile = index // 2
            spalte = index % 2

            kategorien_box.attach(
                checkbox,
                spalte,
                zeile,
                1,
                1
            )


        kategorien_bereich = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(0)
        scroll.set_max_content_height(260)
        scroll.set_propagate_natural_height(True)
        scroll.set_vexpand(False)
        scroll.set_child(kategorien_box)

        kategorien_bereich.append(scroll)

        neue_kategorie_button = Gtk.Button(
            label="+ Neue Kategorie"
        )
        neue_kategorie_button.set_halign(Gtk.Align.START)
        kategorien_bereich.append(neue_kategorie_button)

        kategorien_bereich.set_vexpand(True)
        hauptbox.append(kategorien_bereich)


        def neue_kategorie_hinzufuegen(button):
            eingabe_fenster = Adw.MessageDialog(
                transient_for=fenster,
                modal=True,
                heading="Neue Kategorie",
                body="Wie soll die neue Kategorie heißen?"
            )

            eingabe = Gtk.Entry()
            eingabe.set_placeholder_text("Kategoriename eingeben")
            eingabe_fenster.set_extra_child(eingabe)

            eingabe_fenster.add_response("abbrechen", "Abbrechen")
            eingabe_fenster.add_response("hinzufuegen", "Hinzufügen")
            eingabe_fenster.set_default_response("hinzufuegen")
            eingabe_fenster.set_response_appearance(
                "hinzufuegen",
                Adw.ResponseAppearance.SUGGESTED
            )

            def antwort(dialog, response):
                if response != "hinzufuegen":
                    return

                name = eingabe.get_text().strip()

                if not name:
                    return

                if any(
                    name.casefold() == k.casefold()
                    for k in kategorien
                ):
                    return

                # PHASE 3: Bestehende Grid-Positionen nicht durch Sortieren entwerten.
                kategorien.append(name)

                checkbox = Gtk.CheckButton(label=name)
                checkbox.set_active(True)

                def checkbox_geaendert(checkbutton, name=name):
                    checkbutton.set_inconsistent(False)
                    aenderungen[name] = checkbutton.get_active()

                checkbox.connect("toggled", checkbox_geaendert)
                zeile = (len(kategorien) - 1) // 2
                spalte = (len(kategorien) - 1) % 2

                kategorien_box.attach(
                    checkbox,
                    spalte,
                    zeile,
                    1,
                    1
                )

                # Die neue Kategorie soll zunächst allen
                # ausgewählten Kontakten zugewiesen werden.
                aenderungen[name] = True

            eingabe_fenster.connect("response", antwort)
            eingabe_fenster.present()

        neue_kategorie_button.connect(
            "clicked",
            neue_kategorie_hinzufuegen
        )


        button_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6
        )
        button_box.set_halign(Gtk.Align.END)

        abbrechen_button = Gtk.Button(label="Abbrechen")
        uebernehmen_button = Gtk.Button(label="Übernehmen")
        ok_button = Gtk.Button(label="OK")

        ok_button.add_css_class("suggested-action")

        button_box.append(abbrechen_button)
        button_box.append(uebernehmen_button)
        button_box.append(ok_button)

        hauptbox.append(button_box)

        fenster.set_content(hauptbox)

        abbrechen_button.connect(
            "clicked",
            lambda button: fenster.close()
        )



        # PHASE 1: Alle Speichervorgänge laufen asynchron. Das Dialogfenster
        # bleibt bis zur Bestätigung des Backends geöffnet; kein Doppel-Klick.
        speicherzustand = {"aktiv": False, "schliessen_nach_erfolg": False}

        def aenderungen_speichern(schliessen_nach_erfolg=False):
            print("DEBUG: Funktion aufgerufen", flush=True)
            print("DEBUG: Änderungen vorhanden:", bool(aenderungen), flush=True)
            print("DEBUG: Speichern aktiv:", speicherzustand["aktiv"], flush=True)

            if speicherzustand["aktiv"]:
                return
                print("DEBUG: Speichern-Button wurde ausgelöst", flush=True)
            ausgewaehlte_kontakte = list(self.ausgewaehlte_kontakte)
            ausgewaehlte_uids = {
                (kontakt["adressbuch_uid"], kontakt["uid"])
                for kontakt in ausgewaehlte_kontakte
            }
            # Nur Änderungen (Deltas), nicht veraltete Kategorien-Snapshots
            # ans Backend geben: dieses prüft vor dem Speichern die aktuelle Version.
            kontakt_aenderungen = {
                (kontakt["adressbuch_uid"], kontakt["uid"]): dict(aenderungen)
                for kontakt in ausgewaehlte_kontakte
            }
            speicherzustand["aktiv"] = True
            speicherzustand["schliessen_nach_erfolg"] = schliessen_nach_erfolg
            self._speichern_aktiv = True
            # PHASE 1: Während des Speicherns keine Adressbücher umschalten.
            for schalter in self.adressbuch_switches.values():
                schalter.set_sensitive(False)
            for knopf in (uebernehmen_button, ok_button, abbrechen_button):
                knopf.set_sensitive(False)

            def speichern_fertig(fehler):
                # Callback wird vom Backend garantiert im GTK-Hauptthread ausgeführt.
                speicherzustand["aktiv"] = False
                self._speichern_aktiv = False
                for schalter in self.adressbuch_switches.values():
                    schalter.set_sensitive(True)
                for knopf in (uebernehmen_button, ok_button, abbrechen_button):
                    knopf.set_sensitive(True)
                if fehler:
                    meldung = Adw.MessageDialog(
                        transient_for=fenster, modal=True,
                        heading="Speichern fehlgeschlagen",
                        body=str(fehler)
                    )
                    meldung.add_response("ok", "OK")
                    meldung.present()
                    # Erfolgreiche Teile wurden eventuell bereits gespeichert.
                    # Eine erneute Abfrage vermeidet inkonsistente lokale Daten.
                    self.kontakte_laden_starten(self.aktive_adressbuch_uids())
                    return

                aenderungen.clear()
                # Kontaktobjekte enthalten jetzt nur bestätigte neue Kategorien.
                self.filter_anwenden(self.filter_entry)
                for row, kontakt in self.zeilen_kontakte.items():
                    if (kontakt["adressbuch_uid"], kontakt["uid"]) in ausgewaehlte_uids:
                        self.liste.select_row(row)
                self.kategorien_anzeigen()
                if speicherzustand["schliessen_nach_erfolg"]:
                    fenster.close()


            try:
                print("DEBUG: Starte Backend-Auftrag", flush=True)
                speichere_kategorien_mehrere_async(
                    ausgewaehlte_kontakte, kontakt_aenderungen, speichern_fertig
                )
                print("DEBUG: Backend-Auftrag gestartet", flush=True)
            except Exception as fehler:
                print(f"DEBUG: Fehler beim Start: {fehler}", flush=True)
                speichern_fertig(fehler)


        uebernehmen_button.connect(
            "clicked", lambda button: aenderungen_speichern(False)
        )
        ok_button.connect(
            "clicked", lambda button: aenderungen_speichern(True)
        )

        fenster.present()


    def ueber_categories_anzeigen(self, action, parameter):
        dialog = Adw.AboutDialog()

        dialog.set_application_name("Categories")
        dialog.set_application_icon(
        "io.github.chcervus.Categories"
        )
        dialog.set_version("0.1.0")
        dialog.set_comments(
            "Zweck des Programms ist vCard-Kategorien:\n"
            "• zu verknüpfen und Kontakte zu filtern\n"
            "• zuzuweisen, zu entfernen und neu anzulegen\n"
            "• und zur Adressierung von Emails zu nutzen"
        )
        dialog.set_license(
            ""
            "GNU General Public License v3.0 or later\n\n"
            "This program is provided without any warranty, "
            "to the extent permitted by applicable law. "
            "The authors and contributors accept no liability "
            "for damages arising from the use of this program, "
            "except where liability cannot legally be excluded. "
            "It is provided without even the implied warranty "
            "of MERCHANTABILITY or FITNESS FOR A "
             "PARTICULAR PURPOSE. "
        )
        dialog.set_developer_name("Ch:Hirtz")
        dialog.set_copyright("© 2026")

        dialog.present(self)





class KontaktfilterApp(Adw.Application):

    def __init__(self):

        super().__init__(
            application_id="io.github.chcervus.Categories"
        )


    def do_activate(self):

        window = self.props.active_window

        if window is None:

            window = KontaktfilterWindow(
                application=self
            )

        window.present()


# PHASE 3: Sicherer Import in Unit-Tests und andere Python-Module.
if __name__ == "__main__":
    app = KontaktfilterApp()
    app.run()
