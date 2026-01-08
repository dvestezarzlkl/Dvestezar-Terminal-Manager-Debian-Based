#!/usr/bin/env python3
import os
import libs.JBLibs.helper as hlp
hlp.initLogging(toConsole=True,log_level=hlp.logging.INFO)
log = hlp.getLogger("sftpManager")

import argparse
from libs.JBLibs.sftp import parser
from libs.JBLibs.sftp import ssh

CONFIG_FILE:str="/etc/jb_sftpmanager/config.jsonc"

def main():
    log.info("\n"+"*"*20 + " SFTP Jail Manager Started " + "*"*20)
    
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
    ssh.restart_sshd()
    
    if args.cmd == "install":
        if not os.path.isfile(CONFIG_FILE):
            log.error(f"Config file not found: {CONFIG_FILE}")
            return
        
        log.info(f"Installing SFTP users from file: {CONFIG_FILE}")
        parser.createUserFromJson(CONFIG_FILE)
        rst=True
    elif args.cmd == "uninstall":
        all_un=False
        if not args.user:
            args.all=True
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
            print("\nNo SFTP users found.\n")
        else:
            print("\nSFTP Users:")
            for u in users:
                print(f"- {u.username} (Home: {u.homeDir}")
            print("")
    try:
        if rst:
            ssh.restart_sshd()
    except Exception as e:
        log.exception(e)
        log.error(f"Failed to restart sshd after operations: {e}")
        
    log.info("\n"+"*"*20 + " SFTP Jail Manager Finished " + "*"*20 + "\n")

if __name__ == "__main__":
    main()
