// version: 2.0.3
const hlp = require('./settings_helper.js');
const jb_cfg=hlp.loadMyCFG();

module.exports = {
    https: hlp.getHttps(jb_cfg),
    flowFile: 'flows.json',
    flowFilePretty: true,
    adminAuth: {
        type: "credentials",
        users: jb_cfg.admin_users,
    },
    httpNodeAuth: jb_cfg.ui_user,
    uiPort: jb_cfg.uiPort,
    uiHost: "",
    diagnostics: {
        enabled: true,
        ui: true,
    },
    runtimeState: {
        enabled: false,
        ui: false,
    },
    logging: {
        console: {
            level: "info",
            metrics: false,
            audit: false
        }
    },
    contextStorage: jb_cfg.contextStorage,
    exportGlobalContextKeys: false,
    externalModules: {
    },
    editorTheme: {
    page: {
        title: jb_cfg.webTitle
    },
    header:{
        title: jb_cfg.webTitle
    },
        palette: {
        },
        projects: {
            enabled: true,
            workflow: {
                mode: "manual"
            }
        },
        codeEditor: {
            lib: "monaco",
            options: {
            }
        }
    },
    functionExternalModules: true,
    functionGlobalContext: {
        libs: hlp.loadMyLoader(),
        jb_cfg:jb_cfg.runtime,
    },
    debugMaxLength: 1000,
    mqttReconnectTime: 15000,
    serialReconnectTime: 15000,
}
