#!/usr/bin/env python3
import os
import libs.JBLibs.helper as hlp
hlp.initLogging(toConsole=True,log_level=hlp.logging.INFO)
log = hlp.getLogger("sftpManager")

import argparse
from libs.JBLibs.sftp import parser
from libs.JBLibs.sftp import ssh
from libs.JBLibs.term import en_color, text_color

__VERSION__ = "2.0.0"
CONFIG_FILE_PATH:str="/etc/jb_sftpmanager"
CONFIG_FILE:str="config.jsonc"

def main():
    log.info("\n"+"*"*20 + f" SFTP Jail Manager Started (v{__VERSION__}) " + "*"*20)
    
    ap = argparse.ArgumentParser(description="SFTP jail manager")
    ap.add_argument("-v", "--verbose", action="store_true")

    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_inst = sub.add_parser("install", help="Install SFTP user from config file")
    # ap_inst.add_argument("--file", required=True)

    ap_un = sub.add_parser("uninstall", help="Uninstall SFTP user")
    ap_un.add_argument("--user", required=False, help="Username to uninstall (if not provided, uninstalls all users)")
    # ap_un.add_argument("--all", action="store_true", help="Uninstall all SFTP users")
    
    _ = sub.add_parser("list", help="List all SFTP users")

    args = ap.parse_args()

    rst=False
    
    if not os.path.isdir(CONFIG_FILE_PATH):
        # vytvoříme config adresář pokud neexistuje
        log.info(f"Creating config directory: {CONFIG_FILE_PATH}")
        try:
            os.makedirs(CONFIG_FILE_PATH, exist_ok=True)
        except Exception as e:
            log.error(f"Failed to create config directory: {e}")
            return
        # nakopíruejem default config file z 'assets/sftpManagerExampleConfig.jsonc' jako config.jsonc
        # ale na začítek dám text 'Nový soubor, upravte podle potřeby!\n\n' tak aby při parse byla vyhozena chyba bez potřebných úprav
        example_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sftpManagerExampleConfig.jsonc")
        if not os.path.isfile(example_cfg_path):
            log.error(f"Example config file not found: {example_cfg_path}")
            return
        try:
            with open(example_cfg_path, "r") as f_src:
                content = f_src.read()
            content = "! Nový soubor, upravte podle potřeby!\n\n" + content
            cfg_path = os.path.join(CONFIG_FILE_PATH, CONFIG_FILE)
            with open(cfg_path, "w") as f_dst:
                f_dst.write(content)
            log.info(f"Created example config file at: {cfg_path}")
        except Exception as e:
            log.error(f"Failed to create example config file: {e}")
            return
        
    if args.cmd == "install":
        cfg=os.path.join(CONFIG_FILE_PATH, CONFIG_FILE)
        if not os.path.isfile(cfg):
            log.error(f"Config file not found: {cfg}")
            return

        #otestujeme na text '! Nový soubor, upravte podle potřeby!' na začátku
        try:
            with open(cfg, "r") as f:
                first_line = f.readline()
            if first_line.startswith("! Nový soubor"):
                log.error(f"Config file not configured yet. Please edit the file: {cfg}")
                return
        except Exception as e:
            log.error(f"Failed to read config file: {e}")
            return

        
        ssh.restart_sshd()
        log.info(f"Installing SFTP users from file: {cfg}")
        parser.createUserFromJson(cfg)
        rst=True
        
    elif args.cmd == "uninstall":
        ssh.restart_sshd()
        
        all_un=False
        if not args.user:
            all_un=True
        rst=True
        if all_un:
            log.info("Uninstalling all SFTP users.")
            parser.uninstallAllUsers()
        else:
            u=str(args.user).strip()
            if not u:
                log.error("No username provided for uninstallation.")
                return
            
            log.info(f"Uninstalling SFTP user: {u}")
            parser.uninstallUser(u)
    elif args.cmd == "list":
        log.info("Listing all SFTP users:")
        users = parser.listActiveUsers()
        if not users:
            print(text_color("\nNo SFTP users found.\n",en_color.BRIGHT_RED))
        else:
            print(text_color("\nSFTP Users:\n", en_color.BRIGHT_GREEN))
            for u in users:
                uCl=text_color(u.username, en_color.BRIGHT_CYAN)
                dir=text_color(u.homeDir, en_color.YELLOW)
                print(f"- {uCl} (Home: {dir})")
            print("")
    try:
        if rst is True:
            ssh.restart_sshd()
    except Exception as e:
        log.exception(e)
        log.error(f"Failed to restart sshd after operations: {e}")
        
    log.info("\n"+"*"*20 + " SFTP Jail Manager Finished " + "*"*20 + "\n")

if __name__ == "__main__":
    main()
