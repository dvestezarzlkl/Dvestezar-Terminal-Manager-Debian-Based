TXT_MAIN_NAME = "SSH (&) User Key Management"
TXT_MENU="Menu"
TXT_INCLUDED = "included"
TXT_NOT_INCLUDED = "not included"

TXT_TITLE_01 = "System users"
TXT_TITLE_02 = "Number of users"
TXT_TITLE_03 = "Select user"
TXT_TITLE_04 = "Create system user"
TXT_TITLE_055 = "Key list"
TXT_TITLE_05 = "Select user action"
TXT_TITLE_06 = "Select key action"

TXT_MENU_00 = "no sudo"
TXT_MENU_01 = "sudo access"
TXT_MENU_02 = "key count"

TXT_MENU2_TITLE_01 = "Edit user"
TXT_MENU2_TITLE_02 = "Number of keys"
TXT_MENU2_TITLE_03 = "Create new key"
TXT_MENU2_TITLE_04 = "Delete selected key"
TXT_MENU2_TITLE_05 = "Include key in authorized_keys"
TXT_MENU2_TITLE_06 = "Remove key from authorized_keys"
TXT_MENU2_TITLE_07 = "Show private key"
TXT_MENU2_TITLE_08 = "Delete system user and remove all data"
TXT_MENU2_TITLE_09 = "Change user password"
TXT_MENU2_TITLE_10 = "Update user SSH directory structure"
TXT_MENU2_TITLE_11 = "User SSH directory updated (for manager)"

TXT_MENU2_TITLE_12 = "Remove sudo permissions from user"
TXT_MENU2_TITLE_13 = "Add sudo permissions to user"
TXT_MENU2_TITLE_14 = "Updating user SSH directory structure"
TXT_MENU2_TITLE_15 = "Sudo permissions removed"
TXT_MENU2_TITLE_16 = "Removing sudo permissions from user"
TXT_MENU2_TITLE_17 = "Adding sudo permissions to user"
TXT_MENU2_TITLE_18 = "Sudo permissions added"

TXT_MENU2_TITLE_19 = "Remove user from dialout group (tty)"
TXT_MENU2_TITLE_20 = "Removing user from dialout group (tty)"
TXT_MENU2_TITLE_21 = "User removed from dialout group (tty)"
TXT_MENU2_TITLE_22 = "Add user to dialout group (tty)"
TXT_MENU2_TITLE_23 = "Adding user to dialout group (tty)"
TXT_MENU2_TITLE_24 = "User added to dialout group (tty)"
TXT_MENU2_TITLE_25 = "Error adding user to dialout group (tty)"
TXT_MENU2_TITLE_26 = "Error removing user from dialout group (tty)"
TXT_MENU2_TITLE_27 = "Dialout is the primary group of user {user}. Changing primary group to 'users'."

TXT_MENU3_TITLE_01 = "Edit selected user key"
TXT_MENU3_TITLE_02 = "Key"

TXT_MENU2_TITLE_28 = "Disable sudo without password for user"
TXT_MENU2_TITLE_29 = "Enable sudo without password for user"
TXT_MENU2_TITLE_29_not_available = "Enable sudo without password for user (not available, user is not a sudoer)"
TXT_MENU2_TITLE_30 = "Enable SSH password login for user"
TXT_MENU2_TITLE_31 = "Disable SSH password login for user"
TXT_MENU2_TITLE_31_not_available = "Disable SSH password login for user (not available, user has no keys)"

TXT_MENU2_TITLE_32 = "Enable sudo with password for user"
TXT_MENU2_TITLE_33 = "Now switching to sudo with password will be required for user"
TXT_MENU2_TITLE_34 = "Enable sudo without password for user"
TXT_MENU2_TITLE_35 = "Now switching to sudo without password will not be required for user"

TXT_MENU2_TITLE_36 = "Disable SSH password login for user"
TXT_MENU2_TITLE_37 = "Now SSH password login is disabled for user"
TXT_MENU2_TITLE_38 = "Enable SSH password login for user"
TXT_MENU2_TITLE_39 = "Now SSH password login is enabled for user"

TXT_MENU2_TITLE_40 = "Mail recipient"
TXT_MENU2_TITLE_41 = "not configured"
TXT_MENU2_TITLE_42 = "Set or clear mail recipient"
TXT_MENU2_TITLE_43 = "Enter the mail recipient"
TXT_MENU2_TITLE_44 = "Current address: {mail}\nSubmit an empty value to clear it."
TXT_MENU2_TITLE_45 = "The email address is invalid."
TXT_MENU2_TITLE_46 = "The mail recipient was saved."
TXT_MENU2_TITLE_47 = "The mail recipient was cleared."
TXT_MENU3_TITLE_03 = "Send key by mail"
TXT_MENU3_TITLE_04 = "No mail recipient is configured for this user."
TXT_MENU3_TITLE_05 = "Sending the SSH key by mail..."
TXT_MENU3_TITLE_06 = "The SSH key was sent successfully."

TXT_SSH_MAIL_INVALID_RECIPIENT = "The mail recipient is invalid."
TXT_SSH_MAIL_KEY_READ_FAILED = "Failed to read the key: {error}"
TXT_SSH_MAIL_ZIP_FAILED = "Failed to create the ZIP key attachment: {error}"
TXT_SSH_MAIL_SUBJECT = "SSH terminal access for user {username}: {key_name}"
TXT_SSH_MAIL_SUBJECT_PUBLIC_PRIVATE = " (public + private)"
TXT_SSH_MAIL_SUBJECT_PUBLIC = " (public only)"
TXT_SSH_MAIL_EXPORT_FOR = "SSH terminal and file-transfer access - key '{key_name}', user: {username}"
TXT_SSH_MAIL_ACCESS_PURPOSE = "This ordinary system account allows an interactive SSH terminal login and may also be used for SCP/SFTP file transfer. It is not a restricted SFTP-only account."
TXT_SSH_MAIL_RECIPIENT = "Recipient: {recipient}"
TXT_SSH_MAIL_ARCHIVE_ATTACHED = "The key files and instructions are attached in archive: {filename}"
TXT_SSH_MAIL_PRIVATE_WARNING = "The attached archive contains a private key. Protect it and do not forward it through an unprotected channel."
TXT_SSH_MAIL_NO_PRIVATE_KEY = "No private key is stored for this entry; the archive contains only the public key."
TXT_SSH_MAIL_README_PRIVATE_LINE = "- {private_filename}: private key; keep it secret and never publish it."
TXT_SSH_MAIL_README_NO_PRIVATE_LINE = "- No private key is stored for this entry."
TXT_SSH_MAIL_PRIVATE_PROTECTION = "4. On Linux, protect the private key with: chmod 600 <private-key-file>"
TXT_SSH_MAIL_CLIENT_INSTRUCTIONS = """Terminal / device management:
1. Use the key for a normal SSH login, for example: ssh -i {private_usage} <user>@<server>.
2. The same system account may also be used for SCP/SFTP file transfer.

Total Commander - Secure FTP/SFTP plugin:
1. Set Private key file to {private_usage} in the connection settings.
2. Set Public key file to the matching public key {public_filename}. The plugin requires both files.
3. Leave the Password field empty.

WinSCP:
1. Open Advanced -> SSH -> Authentication.
2. Select {private_usage} in Private key file; this is the file without the .pub suffix.
3. If WinSCP offers to convert the key to PuTTY/PPK format, confirm the conversion and use the converted key.
4. Leave the password field empty.
"""
TXT_SSH_MAIL_CLIENT_INSTRUCTIONS_PUBLIC_ONLY = """This archive does not contain a private key and cannot be used by itself to log in. The public key is intended for authorized_keys on an ordinary SSH account with terminal access, or for configuration verification.
"""
TXT_SSH_MAIL_README = """SSH terminal access package

System user: {username}
SSH Manager key: {key_name}

Access purpose:
{access_purpose}

Files:
- {public_filename}: public key; this file may be shared with the server administrator.
{private_line}

General instructions:
1. Extract this ZIP archive.
2. The server address and any non-standard port are delivered separately. The default SSH port is 22.
3. Leave the password empty unless it was delivered separately.
{private_protection}

{client_instructions}
{generated_by}
"""
TXT_SSH_MAIL_GENERATED_BY = "Generated by SSH Manager - SysApp v{version}."
