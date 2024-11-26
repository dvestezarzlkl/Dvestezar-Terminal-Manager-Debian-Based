var jb_cfg=require('../muj-node-config.js');

function getHttps(){
    if(!jb_cfg.https){
        return null;
    }
    if(!jb_cfg.https.key){
        return null;
    }
    if(!jb_cfg.https.cert){
        return null;
    }
    return {
        key: require("fs").readFileSync(jb_cfg.https.key),
        cert: require("fs").readFileSync(jb_cfg.https.cert)
    }
}

module.exports = {
    https: getHttps(),
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
        jb_cfg:jb_cfg.runtime,
    },
    debugMaxLength: 1000,
    mqttReconnectTime: 15000,
    serialReconnectTime: 15000,
}
