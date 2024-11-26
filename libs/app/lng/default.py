TX_OK               = "OK"
TX_FND              = "Found"
TX_DEF              = "Default"
TX_ABORT            = "Aborted by user."
TX_ERROR            = "ERROR"
TX_BKG_START        = "Starting backup process for"
TX_BKG_ERR0         = "Error creating backup for"
TX_BKG_ERR1         = "No valid home directories found"
TX_BKG_ERR2         = "Error creating 7z backup"
TX_BKG_ERR3         = "No users found for backup."
TX_BKG_ERR4         = "Error creating full 7z backup"
TX_BKG_ERR5         = "User does not exist."
TX_BKG_ERR5_TX      = "User does not exist {name}"
TX_BKG_ERR6         = "User home directory does not exist."
TX_BKG_USER_INCL    = "user(s) to include in full 7z backup."
TX_BKG_ERR6_TX      = "Error updating settings.js for user {name}"

TX_HD_VERSION       = "Config version"
TX_HD_URL           = "Server URL"
TX_HD_BKG_DIR       = "Backup directory"
TX_HD_USER          = "System user"
TX_HD_NODE_USER     = "Node user"
TX_HD_SERV_VER      = "Service file version"
TX_HD_InstanceTitle = "Page title"
TX_HD_SSL_STATUS    = "SSL status"
TX_HD_SSL_CFG       = "config (Verified) enabled"
TX_HD_SSL_SELF      = "Self-signed enabled"
TX_HD_SSL_NAN       = "not set"
TX_HD_USR_NF        = "not found"
TX_HD_USR_TERR      = "type error"

TX_CFG_INI_ERR1     = "Error: System user {name} does not exist."
TX_CFG_INI_ERR2     = "Error: Configuration file {pth} does not exist."
TX_CFG_INI_ERR3     = "Error: Configuration file {pth} is not valid."

TX_CFG_SAVED        = "Configuration file {pth} has been updated."
TX_CFG_SV_RST       = "Restarting systemd service..."
TX_CFG_SV_DONE      = "Configuration has been saved."

TX_CFG_RST_ST       = "Stopping systemd service..."
TX_CFG_RST_STS      = "Starting systemd service..."
TX_CFG_RST_OK       = "Systemd service has been restarted."
TX_CFG_RST_ERR1     = "Error: Failed to restart systemd service {name} at stop."
TX_CFG_RST_ERR2     = "Error: Failed to restart systemd service {name} at start."

TX_INST_HD1         ="Creating new node instance"
TX_INST_HD2         ="System user          "
TX_INST_HD3         ="Password             "
TX_INST_HD4         ="Port                 "
TX_INST_HD5         ="Page Title           "
TX_INST_HD6         ="Type of installation "

TX_INST_INP01       ="TITLE (for admin and UI pages)"
TX_INST_INP02       ="leave empty to use the username"
TX_INST_INP03       ="For system user"

TX_INST_Q1          ="Confirm the new node instance setup"

TX_INST_ERR00       ="Error: Default node archive {pth} does not exist."
TX_INST_ERR01       ="User {username} already exists. Aborting."
TX_INST_ERR02       ="Error creating new node instance: {e}"

TX_INST_MAKE_ERR01  ="Error: Invalid username."
TX_INST_MAKE_ERR02  ="Error: User, UserHome or Instance already exists."
TX_INST_MAKE_ERR03  ="Error creating system user {username}: {e}"
TX_INST_MAKE_ERR04  ="Error: User home directory does not exist."
TX_INST_MAKE_ERR05  ="Error: Asset {asset} does not exist."
TX_INST_MAKE_ERR06  ="Error: Default node archive {pth} does not exist."
TX_INST_MAKE_ERR07  ="Error extracting default node setup: {e}"
TX_INST_MAKE_ERR08  ="Error reading {name}: {e}"
TX_INST_MAKE_ERR09  ="Error writing {name}: {e}"
TX_INST_MAKE_ERR10  ="Error: Service for"
TX_INST_MAKE_ERR10_1 ="does not exist"
TX_INST_MAKE_ERR10_2 ="could not be enabled"
TX_INST_MAKE_ERR10_3 ="could not be started"
TX_INST_MAKE_ERR11  ="Error: Service template file does not exist. Cannot create instance because it cannot be started."

TX_INST_MAKE01      ="Extracting default node setup to {pth}..."
TX_INST_MAKE02      ="Default node setup extracted to {pth}."
TX_INST_MAKE03      ="Moving default node setup to {pth}..."
TX_INST_MAKE04      ="Cleaning up temporary directory..."
TX_INST_MAKE05      ="Setting ownership of home directory..."
TX_INST_MAKE06      ="Updating scripts in user's home directory..."
TX_INST_MAKE07      ="Get service instance..."
TX_INST_MAKE08      ="Creating systemd link, enabling and starting service..."
TX_INST_MAKE09      ="Service enabled, starting..."
TX_INST_MAKE_OK     ="OK:Node instance for {name} has been successfully set up."
TX_INST_MAKE_STR    ="Creating directory structure for {name}..."
TX_INST_MAKE_INST   ="Installing current clean version of Node-RED from the repository..." 

TX_REM_ERR1         ="This user does not have a Node instance set up."
TX_REM_ERR2         ="Usernames do not match. Aborting"
TX_REM_ERR3         ="Error: Service not initialized for user."
TX_REM_ERR4         ="Error: Service does not exist - home user for '{name}' is not a Node instance."
TX_REM_ERR5         ="Error: Service could not be stopped."
TX_REM_ERR6         ="Error: Service could not be disabled."

TX_REM_TXT0         ="Stopping service..."
TX_REM_TXT1         ="Disabling service..."
TX_REM_TXT2         ="Service has been stopped and disabled."
TX_REM_TXT_OK       ="OK:Node instance for {name} has been successfully removed."

TX_BKG_ERR7         ="Error creating or getting backup directory"

TX_BKG_TXT00        ="Creating full 7z backup for {num} users..."
TX_BKG_TXT00_1      ="Creating 7z backup for sys username: {name}"
TX_BKG_TXT01        ="To directory: {pth}"
TX_BKG_TXT02        ="Filename: {name}"

TX_FRESH_ERR0       ="Instance already exists at {path}"
TX_FRESH_ERR1       ="Installation failed with error: {e}"
TX_FRESH_ERR2       ="Unexpected error: {e}"

TX_INST_TYPE_0      ="fresh from repository"
TX_INST_TYPE_1      ="from archive"
TX_INST_TYPE_None   ="not set"

TX_INST_TYPE_Q = (
    "Choose installation type:\n"
    "ESC will cancel the installation."
)
TX_INST_TYPE_INP    ="Installation type: "
TX_INST_TYPE_INP_o1 ="Clean installation from the repository - latest version"
TX_INST_TYPE_INP_o2 ="Installation from an archive"

TXT_MENU_INSTN_del_inst0= "Really delete this system user ?"
TXT_MENU_INSTN_del_inst1= "The system user will be deleted along with their home directory, which will be backed up first. Are you sure you want to proceed?\nReally know what you're doing?\nPress N for begin backup and delete."
TX_REM_CANCEL    = "Deletion canceled."