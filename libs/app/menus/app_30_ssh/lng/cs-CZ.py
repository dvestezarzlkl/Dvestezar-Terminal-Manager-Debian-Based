TXT_MENU2_TITLE_40 = "E-mail příjemce"
TXT_MENU2_TITLE_41 = "nenastaven"
TXT_MENU2_TITLE_42 = "Nastavit nebo zrušit e-mail příjemce"
TXT_MENU2_TITLE_43 = "Zadejte e-mail příjemce"
TXT_MENU2_TITLE_44 = "Aktuální adresa: {mail}\nPrázdným vstupem adresu zrušíte."
TXT_MENU2_TITLE_45 = "E-mailová adresa není platná."
TXT_MENU2_TITLE_46 = "E-mail příjemce byl uložen."
TXT_MENU2_TITLE_47 = "E-mail příjemce byl zrušen."
TXT_MENU3_TITLE_03 = "Odeslat klíč mailem"
TXT_MENU3_TITLE_04 = "Uživatel nemá nastaveného e-mail příjemce."
TXT_MENU3_TITLE_05 = "Odesílám SSH klíč mailem..."
TXT_MENU3_TITLE_06 = "SSH klíč byl úspěšně odeslán."

TXT_SSH_MAIL_INVALID_RECIPIENT = "E-mail příjemce není platný."
TXT_SSH_MAIL_KEY_READ_FAILED = "Klíč se nepodařilo načíst: {error}"
TXT_SSH_MAIL_ZIP_FAILED = "ZIP přílohu s klíčem se nepodařilo vytvořit: {error}"
TXT_SSH_MAIL_SUBJECT = "SSH klíč uživatele {username}: {key_name}"
TXT_SSH_MAIL_SUBJECT_PUBLIC_PRIVATE = " (veřejný + soukromý)"
TXT_SSH_MAIL_SUBJECT_PUBLIC = " (pouze veřejný)"
TXT_SSH_MAIL_EXPORT_FOR = "Export SSH klíče '{key_name}' uživatele: {username}"
TXT_SSH_MAIL_RECIPIENT = "Příjemce: {recipient}"
TXT_SSH_MAIL_ARCHIVE_ATTACHED = "Klíče a návod jsou přiloženy v archivu: {filename}"
TXT_SSH_MAIL_PRIVATE_WARNING = "Přiložený archiv obsahuje soukromý klíč. Chraňte jej a neposílejte jej dál nechráněným kanálem."
TXT_SSH_MAIL_NO_PRIVATE_KEY = "U této položky není uložen soukromý klíč; archiv obsahuje pouze veřejný klíč."
TXT_SSH_MAIL_README_PRIVATE_LINE = "- {private_filename}: soukromý klíč; chraňte jej a nikdy jej nezveřejňujte."
TXT_SSH_MAIL_README_NO_PRIVATE_LINE = "- U této položky není uložen soukromý klíč."
TXT_SSH_MAIL_README_PRIVATE_NOT_AVAILABLE = "není součástí tohoto archivu"
TXT_SSH_MAIL_CLIENT_INSTRUCTIONS = """Total Commander - plugin Secure FTP/SFTP:
1. V nastavení připojení nastavte Private key file na {private_usage}.
2. Public key file nastavte na odpovídající veřejný klíč {public_filename}. Plugin vyžaduje oba soubory.
3. Pole Password ponechte prázdné.

WinSCP:
1. Otevřete Upřesnit -> SSH -> Autorizace.
2. Do pole Soubor se soukromým klíčem vyberte {private_usage}, tedy soubor bez přípony .pub.
3. Pokud WinSCP nabídne převod do vlastního formátu PuTTY/PPK, převod potvrďte a použijte vytvořený klíč.
4. Pole hesla ponechte prázdné.
5. U Samba/SFTP sandboxu oprávnění souborů řídí server. Změna práv z klienta nemá účinek a případné upozornění WinSCP lze vypnout.
"""
TXT_SSH_MAIL_CLIENT_INSTRUCTIONS_PUBLIC_ONLY = """Tento archiv neobsahuje soukromý klíč a nelze jej samostatně použít k přihlášení. Veřejný klíč lze předat správci serveru nebo použít ke kontrole konfigurace.
"""
TXT_SSH_MAIL_README = """Balíček SSH klíče

Systémový uživatel: {username}
Klíč v SSH Manageru: {key_name}

Soubory:
- {public_filename}: veřejný klíč; tento soubor lze předat správci serveru.
{private_line}

Obecné pokyny:
1. Rozbalte tento ZIP archiv.
2. Adresa serveru a případný nestandardní port se předávají samostatně. Výchozí port SFTP/SSH je 22.
3. Heslo ponechte prázdné, pokud nebylo předáno samostatně.
4. V Linuxu soukromý klíč chraňte příkazem: chmod 600 <soubor-soukromého-klíče>

{client_instructions}
{generated_by}
"""
TXT_SSH_MAIL_GENERATED_BY = "Vygenerováno pomocí SSH Manager - SysApp v{version}."
